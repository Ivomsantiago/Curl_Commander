"""Proxy tab — live intercepted traffic, scope-aware, with 'send to' actions.

A thin shell over core.proxy (mitmproxy + own CA). Captured flows land in a
live table; out-of-scope rows are dimmed rather than hidden (transparency).
Each row can be sent to the Repeater or the Intruder — the navigate→capture→
edit→resend/attack loop. Capture ingestion (add_capture) is decoupled from the
proxy so it can be driven in tests without mitmproxy installed.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Checkbox, DataTable, Input, Static, TextArea

from curlcommander.core import scope
from curlcommander.core.request_model import RequestConfig


class ProxyPanel(Widget):
    DEFAULT_CSS = """
    ProxyPanel { height: 1fr; }
    ProxyPanel #px-bar { height: auto; }
    ProxyPanel #px-rules-bar { height: auto; }
    ProxyPanel #px-port { width: 12; }
    ProxyPanel #px-scope { width: 1fr; }
    ProxyPanel #px-auto-drop { width: 1fr; }
    ProxyPanel #px-match-replace { width: 1fr; }
    ProxyPanel #px-ca { height: auto; color: $text-muted; }
    ProxyPanel #px-intercept-container { height: 10; display: none; border-top: solid $warning; }
    ProxyPanel #px-intercept-container.-active { display: block; }
    ProxyPanel #px-intercept-body { height: 1fr; }
    ProxyPanel #px-intercept-actions { height: auto; }
    ProxyPanel DataTable { height: 1fr; }
    """

    class SendToRepeater(Message):
        def __init__(self, config: RequestConfig) -> None:
            super().__init__()
            self.config = config

    class SendToIntruder(Message):
        def __init__(self, config: RequestConfig) -> None:
            super().__init__()
            self.config = config

    class InterceptReady(Message):
        def __init__(self, flow: Any, is_request: bool, event: asyncio.Event) -> None:
            super().__init__()
            self.flow = flow
            self.is_request = is_request
            self.event = event

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._captures: list[RequestConfig] = []
        self._running = False
        self._worker = None
        self._current_intercept_event: asyncio.Event | None = None
        self._current_intercept_flow = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="px-bar"):
            yield Input(value="8080", id="px-port")
            yield Input(placeholder="escopo (hosts, um por linha em arquivo) — opcional", id="px-scope")
            yield Button("Iniciar", id="px-start", variant="primary")
            yield Button("Parar", id="px-stop", variant="error")
            yield Checkbox("Interceptar", value=False, id="px-intercept-toggle")
            yield Button("→ Repeater", id="px-repeater")
            yield Button("→ Intruder", id="px-intruder")
        with Horizontal(id="px-rules-bar"):
            yield Input(placeholder="Auto-Drop hosts (ex: google-analytics.com, telemetry)", id="px-auto-drop", tooltip="Domínios separados por vírgula para dropar automaticamente")
            yield Input(placeholder="Match & Replace (ex: secret=X)", id="px-match-replace", tooltip="Ainda não implementado visualmente")
        yield Static("", id="px-ca")
        with Vertical(id="px-intercept-container"):
            yield Static("Interceptado: ...", id="px-intercept-label")
            yield TextArea("", id="px-intercept-body")
            with Horizontal(id="px-intercept-actions"):
                yield Button("Forward", id="px-forward", variant="success")
                yield Button("Drop", id="px-drop", variant="error")
        yield DataTable(id="px-table")

    def on_mount(self) -> None:
        table = self.query_one("#px-table", DataTable)
        table.add_columns("Host", "Método", "Path", "Status", "Tam.", "Escopo")
        table.cursor_type = "row"
        self._show_ca_hint()

    def _show_ca_hint(self) -> None:
        from curlcommander.core import proxy as proxymod

        try:
            ca = proxymod.ca_cert_path()
        except Exception:
            ca = None  # type: ignore[assignment]
        self.query_one("#px-ca", Static).update(
            f"[dim]CA: {ca}. Confie nela só para testes e remova depois.[/dim]"
            if ca
            else "[dim]Proxy indisponível.[/dim]"
        )

    # -- capture ingestion (decoupled from mitmproxy) -----------------------

    def add_capture(self, config: RequestConfig, status_code: int | None, size: int, in_scope: bool = True) -> None:
        """Append a captured flow to the live table (out-of-scope is dimmed)."""
        self._captures.append(config)
        split = urlsplit(config.url)
        host = split.hostname or ""
        path = split.path or "/"
        if split.query:
            path = f"{path}?{split.query}"
        table = self.query_one("#px-table", DataTable)
        style = "" if in_scope else "dim"
        mark = "sim" if in_scope else "[dim]fora[/dim]"

        def cell(text: str) -> str:
            return f"[{style}]{text}[/{style}]" if style else text

        status_text = str(status_code or "—")
        if status_code and in_scope:
            if status_code >= 500:
                status_text = f"[bold red]{status_code}[/bold red]"
            elif status_code >= 400:
                status_text = f"[red]{status_code}[/red]"
            elif status_code >= 300:
                status_text = f"[yellow]{status_code}[/yellow]"
            elif status_code >= 200:
                status_text = f"[green]{status_code}[/green]"
        elif not in_scope:
            status_text = cell(str(status_code or "—"))

        table.add_row(cell(host), cell(config.method), cell(path), status_text, cell(str(size)), mark)

    def _scope_entries(self) -> list[str]:
        raw = self.query_one("#px-scope", Input).value.strip()
        if not raw:
            return []
        try:
            return scope.load_scope(raw)
        except Exception:
            return [h.strip() for h in raw.replace(",", " ").split() if h.strip()]

    # -- proxy lifecycle ----------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "px-start":
            event.stop()
            self._start()
        elif bid == "px-stop":
            event.stop()
            self._stop()
        elif bid in ("px-repeater", "px-intruder"):
            event.stop()
            self._send_selected(to_intruder=(bid == "px-intruder"))
        elif bid == "px-forward":
            event.stop()
            self._resolve_intercept(drop=False)
        elif bid == "px-drop":
            event.stop()
            self._resolve_intercept(drop=True)

    def _resolve_intercept(self, drop: bool) -> None:
        if self._current_intercept_event and self._current_intercept_flow:
            if drop:
                self._current_intercept_flow.kill()
            else:
                text = self.query_one("#px-intercept-body", TextArea).text
                if self._current_intercept_is_req:
                    self._current_intercept_flow.request.content = text.encode()
                else:
                    if self._current_intercept_flow.response:
                        self._current_intercept_flow.response.content = text.encode()

            self.query_one("#px-intercept-container").remove_class("-active")
            self._current_intercept_event.set()
            self._current_intercept_event = None
            self._current_intercept_flow = None

    def on_proxy_panel_intercept_ready(self, message: InterceptReady) -> None:
        self._current_intercept_flow = message.flow
        self._current_intercept_is_req = message.is_request
        self._current_intercept_event = message.event

        container = self.query_one("#px-intercept-container")
        container.add_class("-active")

        req = message.flow.request
        direction = "Request" if message.is_request else "Response"
        self.query_one("#px-intercept-label", Static).update(
            f"[bold red]Intercepted {direction}:[/bold red] {req.method} {req.url}"
        )

        content = (
            req.content if message.is_request else (message.flow.response.content if message.flow.response else b"")
        )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = repr(content)
        self.query_one("#px-intercept-body", TextArea).load_text(text)

    def _start(self) -> None:
        from curlcommander.core import proxy as proxymod

        if self._running:
            return
        if not proxymod.proxy_available():
            from curlcommander.core import features

            self.query_one("#px-ca", Static).update(f"[yellow]{features.missing_message('proxy')}[/yellow]")
            return
        self._running = True
        self.query_one("#px-ca", Static).update("[green]Proxy iniciando…[/green] " + str(proxymod.ca_cert_path()))
        self._worker = self.app.run_worker(self._proxy_worker(), exclusive=False)

    async def _proxy_worker(self) -> None:
        from curlcommander.core import proxy as proxymod

        port = _to_int(self.query_one("#px-port", Input).value, 8080)
        scope_entries = self._scope_entries()
        sink = _CaptureSink(self, scope_entries)

        async def intercept_hook(flow: Any, is_request: bool) -> None:
            # Auto-Drop Check
            auto_drop_raw = self.query_one("#px-auto-drop", Input).value
            if auto_drop_raw and is_request:
                drops = [d.strip().lower() for d in auto_drop_raw.split(",") if d.strip()]
                host = flow.request.host.lower()
                if any(d in host for d in drops):
                    flow.kill()
                    return

            if not self.query_one("#px-intercept-toggle", Checkbox).value:
                return
            ev = asyncio.Event()
            self.app.call_from_thread(self.post_message, self.InterceptReady(flow, is_request, ev))
            await ev.wait()

        try:
            match_replace = self.query_one("#px-match-replace", Input).value.strip()
            rules = []
            if match_replace:
                for rule in match_replace.split(","):
                    rule = rule.strip()
                    if "=" in rule:
                        k, v = rule.split("=", 1)
                        rules.append(proxymod.MatchReplace(k, v, "req"))
                        rules.append(proxymod.MatchReplace(k, v, "resp"))

            # Capture everything (scope marking is done in the panel for
            # transparency); engagement label from the UI is n/a here.
            await proxymod.run_proxy(port, rules, [], sink, engagement="gui", intercept_hook=intercept_hook)
        except Exception as exc:  # noqa: BLE001
            self.query_one("#px-ca", Static).update(f"[red]Proxy parou:[/red] {exc}")
        finally:
            self._running = False

    def _stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None
        self._running = False
        self.query_one("#px-ca", Static).update("[dim]Proxy parado.[/dim]")

    def _send_selected(self, to_intruder: bool) -> None:
        if not self._captures:
            return
        table = self.query_one("#px-table", DataTable)
        idx = table.cursor_row
        if idx is None or idx >= len(self._captures):
            return
        config = self._captures[idx]
        msg = self.SendToIntruder(config) if to_intruder else self.SendToRepeater(config)
        self.post_message(msg)


class _CaptureSink:
    """A repo-shaped object: core.proxy calls .save(HistoryEntry) per flow."""

    def __init__(self, panel: ProxyPanel, scope_entries: list[str]) -> None:
        self._panel = panel
        self._scope = scope_entries

    def save(self, entry) -> None:  # noqa: ANN001 - HistoryEntry (avoid GUI->storage import cycle)
        cfg = entry.request
        in_scope = True
        if self._scope:
            try:
                in_scope = scope.url_in_scope(cfg.url, self._scope)
            except Exception:
                in_scope = True
        size = len(cfg.body.encode()) if cfg.body else 0
        # Hop back onto the UI thread to mutate widgets safely.
        self._panel.app.call_from_thread(self._panel.add_capture, cfg, entry.status_code, size, in_scope)


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
