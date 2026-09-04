from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical

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
        Binding("ctrl+enter", "send_request", "Send", show=True),
        Binding("ctrl+l", "clear_form", "Clear Form", show=True),
        Binding("ctrl+h", "focus_history", "History", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

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
        with Vertical():
            with Horizontal(id="top-area"):
                yield RequestPanel(id="request-panel")
                with Vertical(id="right-area"):
                    yield ResponsePanel(id="response-panel")
                    yield CurlPanel(id="curl-panel")
            yield HistoryPanel(id="history-panel")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_send_request(self) -> None:
        config = self.query_one(RequestPanel).get_config()
        self._send_request(config)

    def action_clear_form(self) -> None:
        self.query_one(RequestPanel).clear_form()
        self.query_one(ResponsePanel).clear()
        self.query_one(CurlPanel).update_curl("")

    def action_focus_history(self) -> None:
        self.query_one(HistoryPanel).focus()

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_request_panel_request_ready(self, event: RequestPanel.RequestReady) -> None:
        self._send_request(event.config)

    def on_request_panel_config_changed(self, event: RequestPanel.ConfigChanged) -> None:
        try:
            curl_cmd = build_curl(event.config)
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
        self.query_one(CurlPanel).update_curl(curl_cmd)

        result = await send(config)
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
