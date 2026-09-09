"""Tests for response diff generation utility."""

from curlcommander.gui.diff_panel import generate_diff


def test_generate_diff_identical():
    text = "Line 1\nLine 2\nLine 3\n"
    diff = generate_diff(text, text)
    assert diff == ""


def test_generate_diff_different():
    text_a = "Status: 200 OK\nBody: Hello World\n"
    text_b = "Status: 404 Not Found\nBody: Hello World\n"
    diff = generate_diff(text_a, text_b)
    assert "-Status: 200 OK" in diff
    assert "+Status: 404 Not Found" in diff
