"""Diff panel component for comparing HTTP responses side-by-side."""

from __future__ import annotations

import difflib

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static, TextArea

from curlcommander.core.request_model import ResponseResult


def generate_diff(text_a: str, text_b: str) -> str:
    """Generate line-by-line unified diff between two text strings."""
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff = difflib.unified_diff(lines_a, lines_b, fromfile="Response A", tofile="Response B")
    return "".join(diff)


class DiffPanel(Container):
    """Panel displaying unified diff between two HTTP responses."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._res_a: ResponseResult | None = None
        self._res_b: ResponseResult | None = None

    def compose(self) -> ComposeResult:
        yield Static("Response Diff (Select Response A and Response B)", id="diff_title", classes="panel_title")
        yield TextArea("", id="diff_output", read_only=True)

    def set_responses(self, res_a: ResponseResult | None, res_b: ResponseResult | None) -> None:
        self._res_a = res_a
        self._res_b = res_b
        self.update_diff()

    def update_diff(self) -> None:
        text_area = self.query_one("#diff_output", TextArea)
        if not self._res_a or not self._res_b:
            text_area.text = "Select two responses to compare differences."
            return

        header_a = f"HTTP {self._res_a.status_code or 0} {self._res_a.reason}\n" + "\n".join(
            f"{k}: {v}" for k, v in self._res_a.headers.items()
        )
        header_b = f"HTTP {self._res_b.status_code or 0} {self._res_b.reason}\n" + "\n".join(
            f"{k}: {v}" for k, v in self._res_b.headers.items()
        )

        content_a = f"{header_a}\n\n{self._res_a.body}"
        content_b = f"{header_b}\n\n{self._res_b.body}"

        diff_result = generate_diff(content_a, content_b)
        text_area.text = diff_result if diff_result else "Responses are identical."
