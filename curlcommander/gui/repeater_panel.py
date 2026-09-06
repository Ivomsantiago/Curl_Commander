"""Repeater tab — free raw-request editing and resends, many persistent tabs.

Each request sent here becomes its own named sub-tab with an editable raw
request, a resend button, a response viewer, and a stack of every resend so
you can compare successive attempts while tweaking one parameter. All sending
goes through the existing http_client; editing/parsing reuses gui.rawreq.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, Input, Static, TabbedContent, TabPane, TextArea

from curlcommander.core.http_client import send
from curlcommander.core.request_model import RequestConfig
from curlcommander.gui import rawreq
from curlcommander.gui.response_view import ResponseView


class RepeaterTab(Widget):
    """One editable request + its resend history + a response viewer."""

    DEFAULT_CSS = """
    RepeaterTab { height: 1fr; layout: horizontal; }
    RepeaterTab #rt-left { width: 1fr; }
    RepeaterTab #rt-right { width: 1fr; }
    RepeaterTab #rt-request { height: 1fr; }
    RepeaterTab #rt-history { height: 8; border-top: solid $primary; }
    RepeaterTab #rt-actions { height: auto; }
    """

    def __init__(self, config: RequestConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._base_url = rawreq.base_url_of(config.url)
        self._initial_text = rawreq.config_to_text(config)
        self._history: list[str] = []
        self._prev_body: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="rt-left"):
            yield TextArea(self._initial_text, id="rt-request")
            with Horizontal(id="rt-actions"):
                yield Button("Enviar", id="rt-send", variant="primary")
                yield Button("Diff c/ anterior", id="rt-diff")
            yield Static("Reenvios: (nenhum ainda)", id="rt-history")
        with Vertical(id="rt-right"):
            yield ResponseView(id="rt-response")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rt-send":
            event.stop()
            self._send()
        elif event.button.id == "rt-diff":
            event.stop()
            if self._prev_body is not None:
                self.query_one(ResponseView).set_diff(self._prev_body)

    def _send(self) -> None:
        try:
            config = rawreq.text_to_config(self.query_one("#rt-request", TextArea).text, self._base_url)
        except Exception as exc:  # noqa: BLE001 - surface a friendly message
            self.query_one("#rt-history", Static).update(f"[red]Requisição inválida:[/red] {exc}")
            return
        self.app.run_worker(self._send_worker(config), exclusive=True)

    async def _send_worker(self, config: RequestConfig) -> None:
        rv = self.query_one(ResponseView)
        self._prev_body = rv.current_body() if self._history else None
        result = await send(config)
        rv.show_result(result)
        n = len(self._history) + 1
        self._history.append(f"#{n}  {result.status_code or 'ERR'}  {result.size_bytes} B  {result.duration_ms:.0f} ms")
        self.query_one("#rt-history", Static).update("Reenvios:\n" + "\n".join(self._history))

    def send_count(self) -> int:
        return len(self._history)


class RepeaterPanel(Widget):
    """Holds every Repeater sub-tab (Burp's numbered request tabs)."""

    DEFAULT_CSS = """
    RepeaterPanel { height: 1fr; }
    RepeaterPanel #rp-bar { height: auto; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._counter = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="rp-bar"):
            yield Input(placeholder="renomear aba atual…", id="rp-rename")
            yield Button("Renomear", id="rp-rename-btn")
            yield Button("Fechar aba", id="rp-close-btn", variant="error")
        yield TabbedContent(id="rp-tabs")

    def add_request(self, config: RequestConfig, title: str | None = None) -> str:
        """Open a new Repeater sub-tab for a request; returns its pane id."""
        self._counter += 1
        pane_id = f"rep-{self._counter}"
        name = title or f"Req {self._counter}"
        tabs = self.query_one("#rp-tabs", TabbedContent)
        tabs.add_pane(TabPane(name, RepeaterTab(config), id=pane_id))
        tabs.active = pane_id
        return pane_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        tabs = self.query_one("#rp-tabs", TabbedContent)
        if event.button.id == "rp-close-btn":
            event.stop()
            if tabs.active:
                tabs.remove_pane(tabs.active)
        elif event.button.id == "rp-rename-btn":
            event.stop()
            new = self.query_one("#rp-rename", Input).value.strip()
            if new and tabs.active:
                tabs.get_tab(tabs.active).label = new  # type: ignore[assignment]
                self.query_one("#rp-rename", Input).value = ""
