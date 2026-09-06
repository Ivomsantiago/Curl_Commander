from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header

from curlcommander import __version__
from curlcommander.config import DB_PATH
from curlcommander.core.curl_builder import build_curl
from curlcommander.core.http_client import send
from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.gui.curl_panel import CurlPanel
from curlcommander.gui.history_panel import HistoryPanel
from curlcommander.gui.request_panel import RequestPanel
from curlcommander.gui.response_panel import ResponsePanel
from curlcommander.storage.history_repo import HistoryRepo


class CurlCommanderApp(App):
    TITLE = "CurlCommander"
    SUB_TITLE = f"v{__version__}"
    CSS = """
    Screen {
        layout: vertical;
    }
    #top-area {
        height: 3fr;
        layout: horizontal;
    }
    #right-area {
        width: 3fr;
        layout: vertical;
    }
    HistoryPanel {
        height: 14;
    }
    """

    BINDINGS = [
        # Ctrl+Enter is unreliable across terminal emulators; Ctrl+S is the
        # documented, portable primary. Ctrl+Enter kept as a bonus where it works.
        Binding("ctrl+s", "send_request", "Enviar", show=True),
        Binding("ctrl+enter", "send_request", "Enviar", show=False),
        Binding("ctrl+y", "copy_curl", "Copiar curl", show=True),
        Binding("ctrl+x", "cancel_request", "Cancelar", show=True),
        Binding("ctrl+l", "clear_form", "Limpar", show=True),
        Binding("ctrl+h", "focus_history", "Histórico", show=True),
        # Sair: Ctrl+Q e Ctrl+C, com priority para pegar mesmo com foco num
        # Input/TextArea (o widget focado consome o resto, não estes atalhos).
        Binding("ctrl+q", "quit", "Sair", show=True, priority=True),
        Binding("ctrl+c", "quit", "Sair", show=False, priority=True),
    ]

    _last_curl: str = ""
    _last_content: bytes = b""
    _in_flight: bool = False
    _quit_armed: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, db_path=DB_PATH, **kwargs) -> None:
        super().__init__(**kwargs)
        # One connection reused for the whole session, closed on exit (1.11).
        self.repo = HistoryRepo(db_path)

    def on_unmount(self) -> None:
        self.repo.close()

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            with Horizontal(id="top-area"):
                yield RequestPanel(id="request-panel")
                with Vertical(id="right-area"):
                    yield ResponsePanel(id="response-panel")
                    yield CurlPanel(id="curl-panel")
            yield HistoryPanel(id="history-panel")
        yield Footer()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_quit(self) -> None:  # type: ignore[override]
        # Confirm quit only while a request is in flight (never blocks normal
        # exit): first Ctrl+Q arms, second one (or after it finishes) exits.
        if self._in_flight and not self._quit_armed:
            self._quit_armed = True
            self.notify(
                "Requisição em andamento. Pressione Ctrl+Q de novo para sair mesmo assim.",
                severity="warning",
            )
            return
        self.exit()

    def action_send_request(self) -> None:
        config = self.query_one(RequestPanel).get_config()
        self._send_request(config)

    def action_clear_form(self) -> None:
        self.query_one(RequestPanel).clear_form()
        self.query_one(ResponsePanel).clear()
        self.query_one(CurlPanel).update_curl("")

    def action_focus_history(self) -> None:
        self.query_one(HistoryPanel).focus()

    def action_copy_curl(self) -> None:
        from curlcommander.core.clipboard import ClipboardError, write_clipboard

        if not self._last_curl:
            self.notify("Nothing to copy yet.", severity="warning")
            return
        try:
            write_clipboard(self._last_curl)
            self.notify("curl copied to clipboard.")
        except ClipboardError as exc:
            self.notify(str(exc), severity="error")

    def action_cancel_request(self) -> None:
        self.workers.cancel_all()
        self.query_one(ResponsePanel).query_one("#response-status").update("cancelled")

    def on_button_pressed(self, event) -> None:
        if event.button.id == "quit-btn":
            self.action_quit()
            return
        if event.button.id == "clear-btn":
            self.action_clear_form()
            return
        if event.button.id != "save-response-btn":
            return
        if not self._last_content:
            self.notify("No response to save.", severity="warning")
            return
        from pathlib import Path

        out = Path("curlcommander-response.bin")
        out.write_bytes(self._last_content)
        self.notify(f"Response saved to {out}")

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_request_panel_request_ready(self, event: RequestPanel.RequestReady) -> None:
        self._send_request(event.config)

    def on_request_panel_config_changed(self, event: RequestPanel.ConfigChanged) -> None:
        try:
            curl_cmd = build_curl(event.config)
            self._last_curl = curl_cmd
            self.query_one(CurlPanel).update_curl(curl_cmd)
        except Exception:
            pass

    def on_history_panel_replay_requested(self, event: HistoryPanel.ReplayRequested) -> None:
        self.query_one(RequestPanel).set_config(event.entry.request)
        self._send_request(event.entry.request)

    def on_history_panel_show_curl_requested(self, event: HistoryPanel.ShowCurlRequested) -> None:
        self.query_one(CurlPanel).update_curl(event.curl_cmd)

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _send_request(self, config: RequestConfig) -> None:
        self.run_worker(self._send_request_worker(config), exclusive=True)

    async def _send_request_worker(self, config: RequestConfig) -> None:
        from datetime import datetime

        curl_cmd = build_curl(config)
        self._last_curl = curl_cmd
        self.query_one(CurlPanel).update_curl(curl_cmd)

        # Sending indicator (Ctrl+X cancels the exclusive worker).
        self._in_flight = True
        self.query_one(ResponsePanel).query_one("#response-status").update("⏳ enviando…")

        try:
            result = await send(config)
        finally:
            self._in_flight = False
            self._quit_armed = False
        self._last_content = result.content
        self.query_one(ResponsePanel).show_result(result)

        entry = HistoryEntry(
            id=0,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            request=config,
            status_code=result.status_code,
            duration_ms=result.duration_ms,
            curl_cmd=curl_cmd,
        )
        self.repo.save(entry)

        self.query_one(HistoryPanel).refresh_history()
