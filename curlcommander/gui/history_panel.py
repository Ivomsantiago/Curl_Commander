from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label

from curlcommander.core.request_model import HistoryEntry


class HistoryPanel(Widget):
    DEFAULT_CSS = """
    HistoryPanel {
        height: 10;
        border: round $secondary;
        padding: 0 1;
    }
    HistoryPanel Label {
        text-style: bold;
        color: $text-muted;
    }
    #history-table {
        height: 1fr;
    }
    #history-btn-row {
        height: auto;
        margin-top: 1;
    }
    #history-btn-row Button {
        margin-right: 1;
    }
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class ReplayRequested(Message):
        def __init__(self, entry: HistoryEntry) -> None:
            super().__init__()
            self.entry = entry

    class ShowCurlRequested(Message):
        def __init__(self, curl_cmd: str) -> None:
            super().__init__()
            self.curl_cmd = curl_cmd

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    _selected_id: str | None = None
    _entries: dict[str, HistoryEntry]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries = {}

    # ------------------------------------------------------------------
    # Composition & lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Label("History")
        yield DataTable(id="history-table", cursor_type="row")
        with Horizontal(id="history-btn-row"):
            yield Button("Replay", id="replay-btn")
            yield Button("Show Curl", id="show-curl-btn")
            yield Button("Delete", id="delete-btn", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.add_columns("ID", "Timestamp", "Method", "URL", "Status", "ms")
        self.refresh_history()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._selected_id = str(event.row_key.value) if event.row_key else None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._selected_id is None:
            return
        entry = self._entries.get(self._selected_id)
        if entry is None:
            return

        match event.button.id:
            case "replay-btn":
                self.post_message(self.ReplayRequested(entry))
            case "show-curl-btn":
                self.post_message(self.ShowCurlRequested(entry.curl_cmd))
            case "delete-btn":
                self._delete_entry(self._selected_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_history(self) -> None:
        entries = self.app.repo.load()

        self._entries = {str(e.id): e for e in entries}
        self._selected_id = None

        table = self.query_one("#history-table", DataTable)
        table.clear()

        for entry in entries:
            table.add_row(
                str(entry.id),
                entry.timestamp,
                entry.request.method,
                entry.request.url,
                str(entry.status_code or "ERR"),
                f"{entry.duration_ms:.0f}",
                key=str(entry.id),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _delete_entry(self, entry_id: str) -> None:
        self.app.repo.delete_by_id(int(entry_id))
        self.refresh_history()
