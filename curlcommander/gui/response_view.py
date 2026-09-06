"""Reusable response viewer for the Repeater / Intruder / Proxy tabs (1.4).

Pretty / Raw / Headers / Cookies views, a search box that counts and steps
through occurrences ("2/7"), and a simple line diff between two responses.
"""

from __future__ import annotations

import difflib

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, TextArea

from curlcommander.config import DISPLAY_LIMIT_BYTES
from curlcommander.core.request_model import ResponseResult
from curlcommander.core.response_formatter import format_body

_MODES = ["Pretty", "Raw", "Headers", "Cookies"]


def diff_bodies(a: str, b: str) -> str:
    """A unified line diff between two response bodies (empty if identical)."""
    if a == b:
        return ""
    lines = difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile="anterior", tofile="atual", lineterm="")
    return "\n".join(lines)


class ResponseView(Widget):
    DEFAULT_CSS = """
    ResponseView { height: 1fr; }
    ResponseView #rv-tools { height: auto; }
    ResponseView #rv-mode { width: 16; }
    ResponseView #rv-search { width: 1fr; }
    ResponseView #rv-count { width: 10; content-align: center middle; color: $text-muted; }
    ResponseView TextArea { height: 1fr; }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._result: ResponseResult | None = None
        self._matches: list[int] = []  # character offsets of the search term
        self._match_idx: int = 0

    def compose(self) -> ComposeResult:
        yield Label("", id="rv-status")
        with Horizontal(id="rv-tools"):
            yield Select([(m, m) for m in _MODES], value="Pretty", id="rv-mode", allow_blank=False)
            yield Input(placeholder="buscar na resposta…", id="rv-search")
            yield Label("", id="rv-count")
            yield Button("◀", id="rv-prev")
            yield Button("▶", id="rv-next")
        yield TextArea("", read_only=True, id="rv-body")

    # -- data ---------------------------------------------------------------

    def show_result(self, result: ResponseResult) -> None:
        self._result = result
        status = self.query_one("#rv-status", Label)
        if result.error:
            status.update(f"[b red]Erro:[/b red] {result.error}")
        else:
            status.update(
                f"[b]{result.status_code} {result.reason}[/b]  "
                f"[dim]{result.duration_ms:.0f} ms · {result.size_bytes} B[/dim]"
            )
        self._rerender()

    def current_body(self) -> str:
        """The current response body (for diffing successive sends)."""
        return self._result.body if self._result else ""

    # -- rendering ----------------------------------------------------------

    def _text_for_mode(self, mode: str) -> str:
        r = self._result
        if r is None:
            return ""
        if mode == "Headers":
            return "\n".join(f"{k}: {v}" for k, v in r.headers.items())
        if mode == "Cookies":
            cookies = [v for k, v in r.headers.items() if k.lower() == "set-cookie"]
            return "\n".join(cookies) if cookies else "(sem Set-Cookie)"
        if mode == "Raw":
            head = [f"HTTP {r.status_code} {r.reason}"]
            head += [f"{k}: {v}" for k, v in r.headers.items()]
            body = r.body
            return "\n".join(head) + "\n\n" + body
        # Pretty
        return format_body(r.body, r.content_type)

    def _mode(self) -> str:
        val = self.query_one("#rv-mode", Select).value
        return str(val) if val is not Select.BLANK else "Pretty"

    def _rerender(self) -> None:
        text = self._text_for_mode(self._mode())
        if len(text) > DISPLAY_LIMIT_BYTES:
            text = text[:DISPLAY_LIMIT_BYTES] + "\n… (truncado)"
        self.query_one("#rv-body", TextArea).load_text(text)
        self._recount()

    def set_diff(self, previous_body: str) -> None:
        """Replace the view with a diff against a previous body."""
        text = diff_bodies(previous_body, self.current_body()) or "(sem diferenças)"
        self.query_one("#rv-body", TextArea).load_text(text)

    # -- search -------------------------------------------------------------

    def _recount(self) -> None:
        term = self.query_one("#rv-search", Input).value
        body = self.query_one("#rv-body", TextArea).text
        self._matches = _find_offsets(body, term) if term else []
        self._match_idx = 0
        self._update_count_label()
        if self._matches:
            self._move_to_match()

    def _update_count_label(self) -> None:
        label = self.query_one("#rv-count", Label)
        if not self._matches:
            label.update("0/0" if self.query_one("#rv-search", Input).value else "")
        else:
            label.update(f"{self._match_idx + 1}/{len(self._matches)}")

    def _move_to_match(self) -> None:
        if not self._matches:
            return
        offset = self._matches[self._match_idx]
        ta = self.query_one("#rv-body", TextArea)
        loc = _offset_to_location(ta.text, offset)
        ta.move_cursor(loc)
        ta.scroll_cursor_visible()

    def next_match(self) -> None:
        if self._matches:
            self._match_idx = (self._match_idx + 1) % len(self._matches)
            self._update_count_label()
            self._move_to_match()

    def prev_match(self) -> None:
        if self._matches:
            self._match_idx = (self._match_idx - 1) % len(self._matches)
            self._update_count_label()
            self._move_to_match()

    def match_count(self) -> int:
        return len(self._matches)

    # -- events -------------------------------------------------------------

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "rv-mode":
            self._rerender()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "rv-search":
            self._recount()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rv-next":
            self.next_match()
            event.stop()
        elif event.button.id == "rv-prev":
            self.prev_match()
            event.stop()


def _find_offsets(text: str, term: str) -> list[int]:
    if not term:
        return []
    offsets: list[int] = []
    low_text, low_term = text.lower(), term.lower()
    start = 0
    while True:
        idx = low_text.find(low_term, start)
        if idx == -1:
            break
        offsets.append(idx)
        start = idx + 1
    return offsets


def _offset_to_location(text: str, offset: int) -> tuple[int, int]:
    """Char offset → (row, col) for a TextArea selection."""
    prefix = text[:offset]
    row = prefix.count("\n")
    col = offset - (prefix.rfind("\n") + 1)
    return (row, col)
