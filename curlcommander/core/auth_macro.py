"""Reusable auth macro: automated login + single-flight session refresh.

An ``AuthMacro`` performs a login (via a pure HTTP request, or via a real
browser with Playwright when the login needs JS/CSRF), extracts a token and/or
cookies, and applies them to outgoing requests. When a request comes back
looking logged-out (401/403 by default, or a configurable body regex — many
legacy apps return 200 with an HTML "session expired" page), the macro
re-authenticates exactly once under a single-flight lock so a burst of
concurrent 401s triggers only one login.

Design constraints honoured (see the repo conventions):
- Playwright is a lazy, optional dependency (``browser`` extra); the HTTP
  backend works with no extra installed.
- ``{{USER}}``/``{{PASS}}`` and any ``{{VAR}}`` resolve through the same
  ``redaction.reveal_text`` env mechanism the rest of the tool uses.
- ``apply()`` never mutates the caller's RequestConfig; it clones via
  ``RequestConfig.from_dict(cfg.to_dict())``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from curlcommander.core.headers import HeaderList
from curlcommander.core.http_client import send
from curlcommander.core.redaction import reveal_text
from curlcommander.core.request_model import RequestConfig, ResponseResult

_DEFAULT_DIE_STATUS: tuple[int, ...] = (401, 403)


class AuthMacroError(RuntimeError):
    pass


# --- mini JSONPath -------------------------------------------------------

_JP_TOKEN = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")


def json_path(data: Any, path: str) -> Any:
    """Resolve a small JSONPath subset: ``$.a.b``, ``$.data.token``, ``$.r[0].jwt``.

    Uses ``jsonpath-ng`` when the optional ``auth`` extra is installed (full
    syntax), otherwise falls back to this 95%-case resolver.
    """
    try:  # optional, richer engine
        import jsonpath_ng

        matches = jsonpath_ng.parse(path).find(data)
        return matches[0].value if matches else None
    except Exception:
        pass
    p = path[1:] if path.startswith("$") else path
    cur: Any = data
    for key, idx in _JP_TOKEN.findall(p):
        if key:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        else:
            if not isinstance(cur, list):
                return None
            i = int(idx)
            cur = cur[i] if 0 <= i < len(cur) else None
        if cur is None:
            return None
    return cur


# --- session state -------------------------------------------------------


@dataclass
class Session:
    token: str = ""
    cookies: HeaderList = field(default_factory=HeaderList)
    acquired_at: float = 0.0
    valid: bool = False


@dataclass
class AuthMacro:
    """A declarative login macro with single-flight refresh."""

    name: str = "auth"
    backend: str = "http"  # "http" | "browser"
    request: RequestConfig | None = None  # http backend login request
    login_url: str = ""  # browser backend
    steps: list[dict[str, Any]] = field(default_factory=list)  # browser steps
    extract: dict[str, Any] = field(default_factory=dict)
    apply_spec: dict[str, Any] = field(default_factory=dict)
    ttl_seconds: float | None = None
    die_status: tuple[int, ...] = _DEFAULT_DIE_STATUS
    die_regex: str | None = None
    headless: bool = True
    scope_entries: list[str] = field(default_factory=list)
    session: Session = field(default_factory=Session)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    # -- construction -----------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthMacro:
        req = data.get("request")
        die = data.get("die", {})
        return cls(
            name=str(data.get("name", "auth")),
            backend=str(data.get("backend", "http")),
            request=RequestConfig.from_dict(req) if isinstance(req, dict) else None,
            login_url=str(data.get("login_url", "")),
            steps=list(data.get("steps", []) or []),
            extract=dict(data.get("extract", {}) or {}),
            apply_spec=dict(data.get("apply", {}) or {}),
            ttl_seconds=data.get("ttl_seconds"),
            die_status=tuple(die.get("status", _DEFAULT_DIE_STATUS)),
            die_regex=die.get("regex"),
            headless=bool(data.get("headless", True)),
            scope_entries=list(data.get("scope", []) or []),
        )

    @classmethod
    def from_file(cls, path: str) -> AuthMacro:
        text = Path(path).read_text(encoding="utf-8")
        if path.endswith((".yaml", ".yml")):
            import yaml

            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        if not isinstance(data, dict):
            raise AuthMacroError(f"macro de auth inválida em {path}: esperava um objeto no topo")
        return cls.from_dict(data)

    # -- freshness / die-check -------------------------------------------

    def is_stale(self) -> bool:
        """True when a re-login is due. TTL=None never expires by time."""
        if not self.session.valid:
            return True
        if self.ttl_seconds is None:
            return False
        return (time.monotonic() - self.session.acquired_at) > self.ttl_seconds

    def should_refresh(self, result: ResponseResult) -> bool:
        """Does this response look logged-out? (status, or a body regex.)"""
        if result.status_code in self.die_status:
            return True
        if self.die_regex and re.search(self.die_regex, result.body):
            return True
        return False

    # -- apply to a request (never mutates the original) -----------------

    def apply(self, config: RequestConfig) -> RequestConfig:
        clone = RequestConfig.from_dict(config.to_dict())
        header = self.apply_spec.get("header")
        template = self.apply_spec.get("template", "{token}")
        if header:
            clone.headers.set(str(header), str(template).format(token=self.session.token))
        if self.apply_spec.get("cookies"):
            for name, value in self.session.cookies:
                clone.cookies.append(name, value)
        return clone

    # -- login (single-flight) -------------------------------------------

    async def login(self, env: dict[str, str] | None = None) -> None:
        """Authenticate now, unconditionally (still single-flight)."""
        await self.refresh(env, seen_token=self.session.token, force=True)

    async def ensure(self, env: dict[str, str] | None = None) -> None:
        if self.is_stale():
            await self.refresh(env, seen_token=self.session.token)

    async def refresh(self, env: dict[str, str] | None, *, seen_token: str, force: bool = False) -> None:
        """Re-authenticate under a single-flight lock.

        A burst of callers that all saw ``seen_token`` collapses into one real
        login: whoever grabs the lock first refreshes, and the rest notice the
        token already changed and return.
        """
        async with self._lock:
            if not force and self.session.valid and self.session.token != seen_token:
                return  # someone else already refreshed while we waited
            await self._do_login(env or {})

    async def _do_login(self, env: dict[str, str]) -> None:
        if self.backend == "browser":
            token, cookies = await self._login_browser(env)
        else:
            token, cookies = await self._login_http(env)
        self.session = Session(token=token, cookies=cookies, acquired_at=time.monotonic(), valid=True)

    # -- HTTP backend -----------------------------------------------------

    async def _login_http(self, env: dict[str, str]) -> tuple[str, HeaderList]:
        if self.request is None:
            raise AuthMacroError("macro http sem 'request' de login")
        cfg = self._resolved_login_request(env)
        result = await send(cfg)
        if result.error:
            raise AuthMacroError(f"login falhou: {result.error}")
        token = self._extract_token(result)
        cookies = self._extract_cookies(result)
        return token, cookies

    def _resolved_login_request(self, env: dict[str, str]) -> RequestConfig:
        cfg = RequestConfig.from_dict(self.request.to_dict())  # type: ignore[union-attr]
        cfg.url = reveal_text(cfg.url, env)
        cfg.body = reveal_text(cfg.body, env)
        cfg.auth_value = reveal_text(cfg.auth_value, env)
        cfg.headers = HeaderList([(k, reveal_text(v, env)) for k, v in cfg.headers])
        return cfg

    def _extract_token(self, result: ResponseResult) -> str:
        spec = self.extract.get("token")
        if not isinstance(spec, dict):
            return ""
        if "json" in spec:
            try:
                data = json.loads(result.body)
            except json.JSONDecodeError:
                return ""
            value = json_path(data, str(spec["json"]))
            return "" if value is None else str(value)
        if "header" in spec:
            return result.headers.get(str(spec["header"]).lower(), "") or result.headers.get(str(spec["header"]), "")
        if "regex" in spec:
            m = re.search(str(spec["regex"]), result.body)
            return m.group(1) if m and m.groups() else (m.group(0) if m else "")
        return ""

    def _extract_cookies(self, result: ResponseResult) -> HeaderList:
        cookies = HeaderList()
        if not self.extract.get("cookies"):
            return cookies
        for key, value in result.headers.items():
            if key.lower() == "set-cookie":
                pair = value.split(";", 1)[0]
                if "=" in pair:
                    name, _, val = pair.partition("=")
                    cookies.append(name.strip(), val.strip())
        return cookies

    # -- browser backend (optional Playwright) ---------------------------

    async def _login_browser(self, env: dict[str, str]) -> tuple[str, HeaderList]:
        from curlcommander.core import browser

        browser.require_browser()  # raises the PT-BR "instale o extra" message
        captured: dict[str, str] = {}
        token_spec = self.extract.get("token_from_response")

        async with browser.BrowserSession(headless=self.headless, scope_entries=self.scope_entries) as session:
            page = await session.new_page()
            if token_spec:
                self._wire_response_capture(session, token_spec, captured)
            await session.goto(page, reveal_text(self.login_url, env))
            for step in self.steps:
                await self._run_browser_step(page, step, env)
            cookies = HeaderList()
            if self.apply_spec.get("cookies") or self.extract.get("cookies"):
                for c in await session.context.cookies():
                    cookies.append(str(c.get("name", "")), str(c.get("value", "")))
        return captured.get("token", ""), cookies

    def _wire_response_capture(self, session: Any, token_spec: dict[str, Any], captured: dict[str, str]) -> None:
        url_contains = str(token_spec.get("url_contains", ""))
        json_expr = str(token_spec.get("json", "$.token"))

        async def on_response(response: Any) -> None:
            if url_contains and url_contains not in response.url:
                return
            try:
                data = await response.json()
            except Exception:
                return
            value = json_path(data, json_expr)
            if value is not None:
                captured["token"] = str(value)

        session.context.on("response", on_response)

    async def _run_browser_step(self, page: Any, step: dict[str, Any], env: dict[str, str]) -> None:
        if "fill" in step:
            await page.fill(str(step["fill"]), reveal_text(str(step.get("value", "")), env))
        elif "click" in step:
            await page.click(str(step["click"]))
        elif "wait_for" in step:
            await page.wait_for_load_state(str(step["wait_for"]))
        elif "goto" in step:
            await page.goto(reveal_text(str(step["goto"]), env), wait_until="load")
