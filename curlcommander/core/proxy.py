"""Intercepting HTTPS proxy with its own CA (H.4).

Built on mitmproxy (the optional [proxy] extra). Captures in-scope traffic to
the history store, applies match-and-replace rules in flight, and generates a
private CA under ``<config>/ca/`` for the browser/OS to trust. Out-of-scope
hosts are tunnelled without inspection. mitmproxy is imported lazily so the rest
of the tool works without it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from curlcommander.config import app_dir
from curlcommander.core import scope
from curlcommander.core.headers import HeaderList
from curlcommander.core.redaction import redact_config
from curlcommander.core.request_model import HistoryEntry, RequestConfig


class ProxyError(RuntimeError):
    pass


def proxy_available() -> bool:
    try:
        import mitmproxy  # noqa: F401

        return True
    except Exception:
        return False


def require_proxy() -> None:
    if not proxy_available():
        raise ProxyError("the proxy feature needs the optional extra: pip install 'curlcommander[proxy]'")


def ca_dir() -> Path:
    d = app_dir() / "ca"
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)  # the CA private key must not be world-readable
    except OSError:
        pass
    return d


def ca_cert_path() -> Path:
    return ca_dir() / "mitmproxy-ca-cert.pem"


# --- match & replace ------------------------------------------------------


@dataclass
class MatchReplace:
    pattern: str
    replacement: str
    where: str = "both"  # "req" | "resp" | "both"

    def compiled(self) -> re.Pattern[bytes]:
        return re.compile(self.pattern.encode())


def parse_rule(spec: str) -> MatchReplace:
    """Parse ``[where:]pattern==>replacement`` (where in req|resp|both)."""
    where = "both"
    body = spec
    if ":" in spec:
        head, _, rest = spec.partition(":")
        if head in ("req", "resp", "both"):
            where, body = head, rest
    if "==>" not in body:
        raise ProxyError(f"invalid rule (expected 'pattern==>replacement'): {spec!r}")
    pattern, _, replacement = body.partition("==>")
    return MatchReplace(pattern, replacement, where)


def apply_replacements(data: bytes, rules: list[MatchReplace], is_request: bool) -> bytes:
    side = "req" if is_request else "resp"
    for rule in rules:
        if rule.where in (side, "both"):
            data = rule.compiled().sub(rule.replacement.encode(), data)
    return data


def ignore_hosts_regex(scope_entries: list[str]) -> str | None:
    """A regex matching hosts NOT in scope, for mitmproxy's ignore_hosts.

    In-scope hosts are intercepted; everything else is tunnelled untouched.
    """
    if not scope_entries:
        return None
    hosts = "|".join(re.escape(h.lstrip("*.")) for h in scope_entries)
    # Negative lookahead: ignore (tunnel) anything that does not end in a scope host.
    return rf"^(?!.*(?:{hosts})(?::\d+)?$).*$"


# --- flow capture ---------------------------------------------------------


def flow_to_config(flow: Any) -> RequestConfig:
    """Convert a mitmproxy flow's request into a RequestConfig for storage."""
    req = flow.request
    headers = HeaderList([(k, v) for k, v in req.headers.items(multi=True)])
    body = req.get_text(strict=False) or "" if req.content else ""
    return RequestConfig(
        method=req.method, url=req.url, headers=headers, body=body, body_type="raw" if body else "none"
    )


def build_addon(
    scope_entries: list[str],
    rules: list[MatchReplace],
    repo: Any,
    engagement: str = "",
) -> Any:
    """Create a mitmproxy addon that captures in-scope flows and rewrites them."""
    require_proxy()

    class _CaptureAddon:
        def request(self, flow: Any) -> None:
            if scope_entries and not scope.url_in_scope(flow.request.url, scope_entries):
                return
            if rules and flow.request.content:
                flow.request.content = apply_replacements(flow.request.content, rules, is_request=True)

        def response(self, flow: Any) -> None:
            if scope_entries and not scope.url_in_scope(flow.request.url, scope_entries):
                return
            if rules and flow.response and flow.response.content:
                flow.response.content = apply_replacements(flow.response.content, rules, is_request=False)
            self._capture(flow)

        def _capture(self, flow: Any) -> None:
            if repo is None:
                return
            config = redact_config(flow_to_config(flow), {})
            status = flow.response.status_code if flow.response else None
            entry = HistoryEntry(
                id=0,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                request=config,
                status_code=status,
                duration_ms=0.0,
                curl_cmd=f"# captured via proxy (engagement {engagement})",
            )
            try:
                repo.save(entry)
            except Exception:
                pass

    return _CaptureAddon()


async def run_proxy(
    port: int,
    scope_entries: list[str],
    rules: list[MatchReplace],
    repo: Any,
    engagement: str = "",
    launch_browser: bool = False,
) -> None:
    """Run the intercepting proxy until interrupted (Ctrl-C)."""
    require_proxy()
    from mitmproxy.options import Options
    from mitmproxy.tools.dump import DumpMaster

    opts = Options(listen_host="127.0.0.1", listen_port=port, confdir=str(ca_dir()))
    ignore = ignore_hosts_regex(scope_entries)
    if ignore:
        opts.update(ignore_hosts=[ignore])  # type: ignore[no-untyped-call]
    master = DumpMaster(opts)
    master.addons.add(build_addon(scope_entries, rules, repo, engagement))  # type: ignore[no-untyped-call]

    browser_ctx = None
    if launch_browser:
        browser_ctx = await _launch_browser_through(port, scope_entries)
    try:
        await master.run()
    finally:
        if browser_ctx is not None:
            await browser_ctx.__aexit__(None, None, None)


async def _launch_browser_through(port: int, scope_entries: list[str]) -> Any:
    """Open the bundled Chromium routed through the proxy (CA already trusted)."""
    from curlcommander.core.browser import BrowserSession

    session = BrowserSession(headless=False, proxy=f"http://127.0.0.1:{port}", scope_entries=scope_entries)
    await session.__aenter__()
    return session
