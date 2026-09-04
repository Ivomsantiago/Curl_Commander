from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Label, Static


class CurlPanel(Widget):
    DEFAULT_CSS = """
    CurlPanel {
        height: 1fr;
        border: round $warning;
        padding: 0 1;
    }
    CurlPanel Label {
        text-style: bold;
        color: $text-muted;
    }
    CurlPanel ScrollableContainer {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Generated curl")
        with ScrollableContainer():
            yield Static("", id="curl-display")

    def update_curl(self, curl_cmd: str) -> None:
        display = self.query_one("#curl-display", Static)
        if curl_cmd:
            display.update(Syntax(curl_cmd, "bash", theme="monokai", word_wrap=True))
        else:
            display.update("")
