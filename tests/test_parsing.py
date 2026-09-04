"""Regression tests for Phase 1.7 — centralized header/param parsing."""

import types

import pytest

from curlcommander.cli import runner
from curlcommander.core.parsing import ParseError, parse_header, parse_headers, parse_param


def test_header_without_space_after_colon_is_parsed():
    # Previously "-H Accept:application/json" produced {} silently.
    assert parse_header("Accept:application/json") == ("Accept", "application/json")


def test_header_with_space_is_parsed():
    assert parse_header("Accept: application/json") == ("Accept", "application/json")


def test_header_value_may_contain_colons():
    assert parse_header("Host: example.com:8080") == ("Host", "example.com:8080")


def test_malformed_header_raises():
    with pytest.raises(ParseError):
        parse_header("no-colon-here")


def test_empty_header_name_raises():
    with pytest.raises(ParseError):
        parse_header(": value")


def test_param_splits_first_equals():
    assert parse_param("a=b=c") == ("a", "b=c")


def test_malformed_param_raises():
    with pytest.raises(ParseError):
        parse_param("noequals")


def test_parse_headers_skips_blank_lines():
    hl = parse_headers(["A: 1", "", "  ", "B:2"])
    assert hl.items() == [("A", "1"), ("B", "2")]


def _args(**over):
    base = dict(
        subcommand=None, url="https://x/y", method="GET", headers=["bad-header"], params=[],
        body="", body_file=None, json_body=None, form_body=None,
        auth_bearer=None, auth_basic=None, auth_apikey=None, proxy=None,
        retry=0, retry_delay=0.0, compressed=False, http2=False, output="",
        pretty=False, env_file=None, no_redirect=False, no_verify=False,
        timeout=30.0, fail=False, curl_only=True, save=False, gui=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def test_cli_malformed_header_is_usage_error(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    assert runner.run_cli(_args()) == runner.EXIT_USAGE
