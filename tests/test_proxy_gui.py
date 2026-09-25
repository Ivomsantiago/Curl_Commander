"""Tests for GUI proxy-panel helpers that don't require mitmproxy.

The Match & Replace parser turns the panel's free-text field into core
MatchReplace rules; it uses only parse_rule/MatchReplace (pure), so unlike
test_proxy.py it isn't gated behind the [proxy] extra.
"""

from curlcommander.gui.proxy_panel import _parse_match_replace


def test_parse_match_replace_official_and_kv_syntax():
    rules = _parse_match_replace("secret==>X, req:foo==>bar, token=REDACTED")
    assert len(rules) == 3
    assert rules[0].pattern == "secret" and rules[0].replacement == "X" and rules[0].where == "both"
    assert rules[1].where == "req" and rules[1].pattern == "foo"
    assert rules[2].pattern == "token" and rules[2].replacement == "REDACTED" and rules[2].where == "both"


def test_parse_match_replace_skips_malformed():
    assert _parse_match_replace("") == []
    assert _parse_match_replace("   ,  ") == []
    assert _parse_match_replace("justtext") == []
