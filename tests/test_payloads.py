"""Tests for the built-in payload library (2B.4 scaffold)."""

import pytest

from curlcommander.core import payloads


def test_available_sets():
    assert {"sqli", "xss", "ssti", "traversal", "cmdi"} <= set(payloads.available())


def test_load_sqli_has_entries():
    entries = payloads.load("sqli")
    assert entries and any("OR" in e.upper() for e in entries)


def test_load_unknown_raises():
    with pytest.raises(KeyError):
        payloads.load("nope")


def test_reflection_heuristic():
    assert payloads.reflects("<script>alert(1)</script>", "before <script>alert(1)</script> after")
    assert not payloads.reflects("<script>", "escaped &lt;script&gt;")
