from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static, TabbedContent, TabPane
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from curlcommander.config import DISPLAY_LIMIT_BYTES
from curlcommander.core.request_model import ResponseResult
from curlcommander.core.response_formatter import format_body, get_lexer


class ResponsePanel(Widget):
    DEFAULT_CSS = """
    ResponsePanel {
        height: 2fr;
        border: round $success;
        padding: 0 1;
        overflow-y: auto;
    }
    ResponsePanel Label {
        text-style: bold;
        color: $text-muted;
    }
    #response-tools {
        height: auto;
    }
    #response-search {
        width: 1fr;
    }
    #response-body-scroll, #response-raw-scroll {
        height: 1fr;
    }
    """

    _result: ResponseResult | None = None

    def compose(self) -> ComposeResult:
        yield Label("Response")
        yield Static("", id="response-status")
        with Horizontal(id="response-tools"):
            yield Input(placeholder="search body…", id="response-search")
            yield Button("Save", id="save-response-btn")
        with TabbedContent(id="response-tabs"):
            with TabPane("Body", id="tab-body"):
                with ScrollableContainer(id="response-body-scroll"):
                    yield Static("", id="response-body")
            with TabPane("Headers", id="tab-headers"):
                yield Static("", id="response-headers")
            with TabPane("Raw", id="tab-raw"):
                with ScrollableContainer(id="response-raw-scroll"):
                    yield Static("", id="response-raw")
            with TabPane("Cookies", id="tab-cookies"):
                yield Static("", id="response-cookies")

    def show_result(self, result: ResponseResult) -> None:
        self._result = result
        if result.error:
            self.query_one("#response-status", Static).update(
                Text(f"Error: {result.error}", style="bold red")
            )
            for id_ in ("#response-body", "#response-headers", "#response-raw", "#response-cookies"):
                self.query_one(id_, Static).update("")
            return

        style = _status_style(result.status_code)
        status_text = Text()
        status_text.append(f"{result.status_code} {result.reason}", style=f"bold {style}")
        status_text.append(f"   {result.duration_ms:.0f} ms  {result.size_bytes} B", style="dim")
        self.query_one("#response-status", Static).update(status_text)

        # Headers tab
        header_table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
        header_table.add_column("Header", style="cyan", no_wrap=True)
        header_table.add_column("Value")
        for k, v in result.headers.items():
            header_table.add_row(k, v)
        self.query_one("#response-headers", Static).update(header_table)

        # Cookies tab (Set-Cookie headers)
        cookies = [v for k, v in result.headers.items() if k.lower() == "set-cookie"]
        self.query_one("#response-cookies", Static).update(
            "\n".join(cookies) if cookies else Text("(no Set-Cookie)", style="dim")
        )

        # Raw tab (status line + headers + body, truncated for display)
        raw = self._raw_view(result)
        self.query_one("#response-raw", Static).update(raw)

        self._render_body(result, filter_text="")

    def _render_body(self, result: ResponseResult, filter_text: str) -> None:
        body = result.body
        if filter_text:
            body = "\n".join(line for line in body.splitlines() if filter_text.lower() in line.lower())
        formatted = format_body(body, result.content_type)
        if len(formatted) > DISPLAY_LIMIT_BYTES:
            formatted = formatted[:DISPLAY_LIMIT_BYTES] + "\n… truncated"
        if formatted:
            self.query_one("#response-body", Static).update(
                Syntax(formatted, get_lexer(result.content_type), theme="monokai", word_wrap=True)
            )
        else:
            self.query_one("#response-body", Static).update("")

    @staticmethod
    def _raw_view(result: ResponseResult) -> str:
        lines = [f"HTTP {result.status_code} {result.reason}"]
        lines += [f"{k}: {v}" for k, v in result.headers.items()]
        lines.append("")
        body = result.body
        if len(body) > DISPLAY_LIMIT_BYTES:
            body = body[:DISPLAY_LIMIT_BYTES] + "\n… truncated"
        lines.append(body)
        return "\n".join(lines)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "response-search" and self._result:
            self._render_body(self._result, event.value)

    def clear(self) -> None:
        self._result = None
        for id_ in ("#response-status", "#response-headers", "#response-body", "#response-raw", "#response-cookies"):
            self.query_one(id_, Static).update("")


def _status_style(status_code: int | None) -> str:
    if status_code is None:
        return "red"
    if status_code < 300:
        return "green"
    if status_code < 400:
        return "yellow"
    return "red"
