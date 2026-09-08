"""WebSocket tab (item 9.5) — two-column sent/received log over core.ws_client.

A thin wiring layer over core.ws_client.WSClient (extra ``ws``), same
convention as the other new tabs. One message in, one reply out per Enviar
(matching the CLI's ``ws connect`` REPL semantics — WSClient pairs each send
with the very next inbound frame), rendered side by side rather than
interleaved in one scrollback.
"""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, RichLog, Static


class WSPanel(Widget):
    DEFAULT_CSS = """
    WSPanel { height: 1fr; layout: vertical; padding: 0 1; }
    WSPanel #ws-bar, WSPanel #ws-send-bar { height: auto; }
    WSPanel #ws-url { width: 1fr; }
    WSPanel #ws-columns { height: 1fr; }
    WSPanel #ws-sent-col, WSPanel #ws-recv-col { width: 1fr; }
    WSPanel RichLog { height: 1fr; border: round $panel; }
    WSPanel #ws-status { height: auto; color: $text-muted; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="ws-bar"):
            yield Input(placeholder="ws:// ou wss://alvo/socket", id="ws-url")
            yield Button("Conectar", id="ws-connect", variant="primary")
            yield Button("Desconectar", id="ws-disconnect", variant="error")
        with Horizontal(id="ws-columns"):
            with Vertical(id="ws-sent-col"):
                yield Static("Enviado")
                yield RichLog(id="ws-sent", wrap=True)
            with Vertical(id="ws-recv-col"):
                yield Static("Recebido")
                yield RichLog(id="ws-recv", wrap=True)
        with Horizontal(id="ws-send-bar"):
            yield Input(placeholder="mensagem", id="ws-message")
            yield Button("Enviar", id="ws-send", variant="primary")
        yield Static("[dim]desconectado[/dim]", id="ws-status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ws-connect":
            event.stop()
            self._connect()
        elif event.button.id == "ws-disconnect":
            event.stop()
            self.app.run_worker(self._disconnect(), exclusive=False)
        elif event.button.id == "ws-send":
            event.stop()
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ws-message":
            self._send()

    def _status(self, text: str) -> None:
        self.query_one("#ws-status", Static).update(text)

    def _connect(self) -> None:
        from curlcommander.core.ws_client import ws_available

        if not ws_available():
            from curlcommander.core import features

            self._status(f"[yellow]{features.missing_message('ws')}[/yellow]")
            return

        url = self.query_one("#ws-url", Input).value.strip()
        if not url:
            self._status("[red]Informe a URL do WebSocket.[/red]")
            return

        scope_entries = getattr(self.app, "scope_entries", []) or []
        if scope_entries:
            from curlcommander.core import scope

            host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
            try:
                scope.enforce(host, scope_entries)
            except scope.ScopeError as exc:
                self._status(f"[red bold]Recusado:[/red bold] {exc}")
                return

        self._status("[dim]conectando…[/dim]")
        self.app.run_worker(self._connect_worker(url), exclusive=False)

    async def _connect_worker(self, url: str) -> None:
        from curlcommander.core.ws_client import WSClient, WSError

        client = WSClient(url)
        try:
            await client.connect()
        except WSError as exc:
            self._status(f"[red bold]Erro:[/red bold] {exc}")
            return
        self._client = client
        self._status(f"[green]conectado[/green] {url}")

    async def _disconnect(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._status("[dim]desconectado[/dim]")

    def _send(self) -> None:
        if self._client is None:
            self._status("[yellow]Conecte antes de enviar.[/yellow]")
            return
        message = self.query_one("#ws-message", Input).value
        if not message:
            return
        self.app.run_worker(self._send_worker(message), exclusive=False)

    async def _send_worker(self, message: str) -> None:
        client = self._client
        if client is None:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self.query_one("#ws-sent", RichLog).write(f"[dim]{ts}[/dim] {message}")
        result = await client.send_message(message)
        ts = datetime.now().strftime("%H:%M:%S")
        if result.error:
            self.query_one("#ws-recv", RichLog).write(f"[dim]{ts}[/dim] [red]{result.error}[/red]")
        else:
            self.query_one("#ws-recv", RichLog).write(f"[dim]{ts}[/dim] {result.body}")
