"""Validate tab (item 9.1) — a form-based surface over core.validators.*.

A thin GUI wiring layer, same convention as ProxyPanel/IntruderPanel: talks to
core directly (validate_cors/validate_open_redirect/validate_xss/
validate_clickjacking/validate_csrf/validate_ssrf/core.idor.check_idor), never
to cli/runner.py. Verdict colours match the CLI exactly (CONFIRMED=red bold,
REFLECTED=yellow, NOT_VULNERABLE=green, ERROR=red bold; IDOR's lowercase
confirmed/blocked/suspect keep confirmed=red, blocked=green, suspect=yellow) —
see cli/runner.py's inline colour dicts, which this mirrors rather than
imports (they're presentation, not shared logic).

Engagement/scope/auth-macro come from the app-level status bar (9.4), not a
per-panel copy of those fields.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static, Switch

from curlcommander.core import scope
from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import parse_header

_KINDS = ["xss", "cors", "open-redirect", "clickjacking", "csrf", "ssrf", "idor"]
_BROWSER_KINDS = {"xss", "clickjacking", "csrf"}
_HTTP_VERDICT_COLOUR = {"CONFIRMED": "red", "REFLECTED": "yellow", "NOT_VULNERABLE": "green", "ERROR": "red"}
_IDOR_VERDICT_COLOUR = {"confirmed": "red", "blocked": "green", "suspect": "yellow"}


def _credentials(cookie_spec: str, bearer: str, header_spec: str) -> tuple[HeaderList, HeaderList]:
    """Mirror cli/runner.py::_validate_credentials for the GUI's own inputs."""
    extra_headers = HeaderList()
    if bearer:
        extra_headers.append("Authorization", f"Bearer {bearer}")
    if header_spec:
        k, v = parse_header(header_spec)
        extra_headers.append(k, v)

    cookies = HeaderList()
    for c in cookie_spec.split(";"):
        c = c.strip()
        if not c:
            continue
        k, _, v = c.partition("=")
        cookies.append(k.strip(), v)
    return extra_headers, cookies


def _http_headers(extra_headers: HeaderList, cookies: HeaderList) -> HeaderList:
    headers = extra_headers.copy()
    if cookies:
        headers.append("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    return headers


class ValidatePanel(Widget):
    DEFAULT_CSS = """
    ValidatePanel { height: 1fr; layout: vertical; padding: 0 1; }
    ValidatePanel #va-form { height: auto; }
    ValidatePanel #va-kind { width: 20; }
    ValidatePanel #va-url { width: 1fr; }
    ValidatePanel .va-row { height: auto; }
    ValidatePanel .va-extra { height: auto; }
    ValidatePanel #va-result { height: 1fr; border: round $panel; padding: 1; overflow-y: auto; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_engagement: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="va-form"):
            with Horizontal(classes="va-row"):
                yield Select([(k, k) for k in _KINDS], value="xss", id="va-kind", allow_blank=False)
                yield Input(placeholder="URL alvo (§PAYLOAD§/§DEST§/FUZZ_OOB/RESOURCE_ID)", id="va-url")
            with Horizontal(classes="va-row"):
                yield Input(placeholder="cookies (k=v; k2=v2)", id="va-cookies")
                yield Input(placeholder="Bearer token", id="va-bearer")
                yield Input(placeholder="header extra (K: V)", id="va-header")
            with Horizontal(id="va-cors-fields", classes="va-extra"):
                yield Input(placeholder="origem atacante", value="https://evil.example", id="va-origin")
            with Horizontal(id="va-browser-fields", classes="va-extra"):
                yield Static("navegador visível:")
                yield Switch(id="va-headed")
                yield Input(placeholder="diretório de evidência (opcional)", id="va-evidence")
            with Horizontal(id="va-ssrf-fields", classes="va-extra"):
                yield Input(placeholder="parâmetro (opcional)", id="va-param")
                yield Input(placeholder="servidor interactsh (opcional)", id="va-interactsh")
                yield Input(placeholder="espera (s)", value="15", id="va-wait")
                yield Static("entendo o OOB público:")
                yield Switch(id="va-oob-consent")
            with Horizontal(id="va-idor-fields", classes="va-extra"):
                yield Input(placeholder="IDs (101,102,103)", id="va-ids")
                yield Input(placeholder="macro de login A (dono)", id="va-auth-a")
                yield Input(placeholder="macro de login B (atacante)", id="va-auth-b")
                yield Input(placeholder="limiar", value="0.85", id="va-threshold")
            yield Button("Validar", id="va-run", variant="primary")
        yield Static("", id="va-result")

    def on_mount(self) -> None:
        self._sync_visible_fields("xss")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "va-kind":
            self._sync_visible_fields(str(event.value))

    def _sync_visible_fields(self, kind: str) -> None:
        self.query_one("#va-cors-fields").display = kind == "cors"
        self.query_one("#va-browser-fields").display = kind in _BROWSER_KINDS
        self.query_one("#va-ssrf-fields").display = kind == "ssrf"
        self.query_one("#va-idor-fields").display = kind == "idor"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "va-run":
            event.stop()
            self._run()

    def _result(self) -> Static:
        return self.query_one("#va-result", Static)

    def _run(self) -> None:
        kind = str(self.query_one("#va-kind", Select).value)
        url = self.query_one("#va-url", Input).value.strip()
        if not url:
            self._result().update("[red]Informe a URL alvo.[/red]")
            return

        engagement = getattr(self.app, "engagement", "") or ""
        if not engagement:
            self._result().update("[red]Defina um engajamento na barra de status primeiro.[/red]")
            return

        scope_entries = getattr(self.app, "scope_entries", []) or []
        if scope_entries:
            try:
                scope.enforce(url, scope_entries)
            except scope.ScopeError as exc:
                self._result().update(f"[red bold]Recusado:[/red bold] {exc}")
                return

        self._result().update("[dim]Validando…[/dim]")
        self.app.run_worker(self._run_worker(kind, url, engagement, scope_entries), exclusive=True)

    async def _run_worker(self, kind: str, url: str, engagement: str, scope_entries: list[str]) -> None:
        try:
            if kind == "idor":
                await self._run_idor(url, engagement)
            elif kind == "ssrf":
                await self._run_ssrf(url, engagement)
            else:
                await self._run_single(kind, url, engagement, scope_entries)
        except Exception as exc:  # noqa: BLE001 - surface a clean message, never a traceback
            self._result().update(f"[red bold]Erro:[/red bold] {exc}")

    async def _run_single(self, kind: str, url: str, engagement: str, scope_entries: list[str]) -> None:
        from curlcommander.core.validation_store import persist_validation

        cred_headers, cred_cookies = _credentials(
            self.query_one("#va-cookies", Input).value,
            self.query_one("#va-bearer", Input).value.strip(),
            self.query_one("#va-header", Input).value.strip(),
        )

        if kind == "cors":
            from curlcommander.core.validators.cors import validate_cors

            result = await validate_cors(
                url,
                origin=self.query_one("#va-origin", Input).value.strip() or "https://evil.example",
                headers=_http_headers(cred_headers, cred_cookies),
            )
        elif kind == "open-redirect":
            from curlcommander.core.validators.redirect import validate_open_redirect

            result = await validate_open_redirect(url, headers=_http_headers(cred_headers, cred_cookies))
        else:
            from curlcommander.core import browser
            from curlcommander.core.browser import BrowserSession

            if not browser.browser_available():
                from curlcommander.core import features

                self._result().update(f"[yellow]{features.missing_message('browser')}[/yellow]")
                return

            evidence_dir = self.query_one("#va-evidence", Input).value.strip()
            shot = f"{evidence_dir}/{kind}.png" if evidence_dir else None
            if evidence_dir:
                from pathlib import Path

                Path(evidence_dir).mkdir(parents=True, exist_ok=True)

            async with BrowserSession(
                headless=not self.query_one("#va-headed", Switch).value,
                scope_entries=scope_entries,
                cookies=cred_cookies or None,
                extra_headers=cred_headers or None,
            ) as session:
                if kind == "xss":
                    from curlcommander.core.validators.xss import validate_xss

                    result = await validate_xss(session, url, screenshot_path=shot)
                elif kind == "clickjacking":
                    from curlcommander.core.validators.clickjacking import validate_clickjacking

                    result = await validate_clickjacking(session, url, screenshot_path=shot)
                else:
                    from curlcommander.core.validators.csrf import validate_csrf

                    result = await validate_csrf(session, url, screenshot_path=shot)

        colour = _HTTP_VERDICT_COLOUR.get(result.verdict, "white")
        detail = f" — {result.detail}" if result.detail else ""
        self._result().update(f"[{colour} bold]{result.verdict}[/{colour} bold] {kind}{detail}")
        persist_validation(engagement, result, self.app.db_path)  # type: ignore[attr-defined]

    async def _run_ssrf(self, url: str, engagement: str) -> None:
        from curlcommander.core.oob.interactsh import InteractshClient, oob_available
        from curlcommander.core.validation_store import persist_validation
        from curlcommander.core.validators.ssrf import validate_ssrf

        if not oob_available():
            from curlcommander.core import features

            self._result().update(f"[yellow]{features.missing_message('oob')}[/yellow]")
            return

        server = self.query_one("#va-interactsh", Input).value.strip() or "oast.pro"
        public_servers = {"oast.pro", "oast.live", "oast.fun", "interact.sh"}
        if server in public_servers and not self.query_one("#va-oob-consent", Switch).value:
            self._result().update(
                "[red bold]Confirmação necessária:[/red bold] marque 'entendo o OOB público' ou "
                "aponte para uma instância própria — metadados de conexão do alvo trafegam por "
                f"{server} (infraestrutura de terceiros)."
            )
            return

        wait_raw = self.query_one("#va-wait", Input).value.strip()
        try:
            wait_timeout = float(wait_raw) if wait_raw else 15.0
        except ValueError:
            wait_timeout = 15.0

        client = InteractshClient(server=server)
        await client.register()
        try:
            result = await validate_ssrf(
                url, client, param=self.query_one("#va-param", Input).value.strip(), wait_timeout=wait_timeout
            )
        finally:
            await client.deregister()

        colour = _HTTP_VERDICT_COLOUR.get(result.verdict, "white")
        self._result().update(f"[{colour} bold]{result.verdict}[/{colour} bold] ssrf — {result.detail}")
        persist_validation(engagement, result, self.app.db_path)  # type: ignore[attr-defined]

    async def _run_idor(self, url: str, engagement: str) -> None:
        from curlcommander.core.auth_macro import AuthMacro
        from curlcommander.core.idor import CONFIRMED, check_idor
        from curlcommander.core.request_model import RequestConfig
        from curlcommander.core.validation_store import persist_validation
        from curlcommander.core.validators.base import CONFIRMED as VR_CONFIRMED
        from curlcommander.core.validators.base import ValidationResult

        ids = [i.strip() for i in self.query_one("#va-ids", Input).value.split(",") if i.strip()]
        if not ids:
            self._result().update("[red]Informe IDs de recurso (ex.: 101,102,103).[/red]")
            return
        if "RESOURCE_ID" not in url:
            self._result().update("[red]A URL precisa conter o marcador RESOURCE_ID.[/red]")
            return

        auth_a_path = self.query_one("#va-auth-a", Input).value.strip()
        auth_b_path = self.query_one("#va-auth-b", Input).value.strip()
        auth_a = AuthMacro.from_file(auth_a_path) if auth_a_path else None
        auth_b = AuthMacro.from_file(auth_b_path) if auth_b_path else None

        threshold_raw = self.query_one("#va-threshold", Input).value.strip()
        try:
            threshold = float(threshold_raw) if threshold_raw else 0.85
        except ValueError:
            threshold = 0.85

        import os

        template = RequestConfig(method="GET", url=url)
        findings = await check_idor(template, ids, auth_a, auth_b, threshold=threshold, env=dict(os.environ))

        lines = []
        for f in findings:
            c = _IDOR_VERDICT_COLOUR.get(f.verdict, "yellow")
            lines.append(f"[{c} bold]{f.verdict.upper()}[/{c} bold] id={f.resource_id} A={f.status_a} B={f.status_b}")
            if f.verdict == CONFIRMED:
                result = ValidationResult(
                    category="idor",
                    verdict=VR_CONFIRMED,
                    url=url.replace("RESOURCE_ID", f.resource_id),
                    detail=f.note,
                    payload=f"RESOURCE_ID={f.resource_id}",
                    evidence={"status_a": f.status_a, "status_b": f.status_b, "similarity": round(f.similarity, 3)},
                )
                persist_validation(engagement, result, self.app.db_path)  # type: ignore[attr-defined]
        self._result().update("\n".join(lines) if lines else "[dim]Nenhum resultado.[/dim]")
