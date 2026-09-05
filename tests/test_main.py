"""Tests for 3.3 main.py subcommand-vs-URL detection and exit propagation."""

import sys

import pytest

import curlcommander.main as main_mod
from curlcommander.cli.arg_parser import SUBCOMMANDS, build_request_parser, build_subcommand_parser


def test_subcommands_frozenset():
    assert SUBCOMMANDS == frozenset({"history", "replay", "curl", "export-history", "delete-history", "clear-history"})


def test_positional_url_is_not_a_subcommand():
    # A URL positional must go to the request parser, never the subcommand one.
    args = build_request_parser().parse_args(["https://example.com/history"])
    assert args.url == "https://example.com/history"


def test_subcommand_parser_parses_history():
    args = build_subcommand_parser().parse_args(["history"])
    assert args.subcommand == "history"


def test_main_propagates_exit_code(monkeypatch, tmp_path):
    # `curl` on an empty DB returns EXIT_USAGE(1); main must sys.exit it.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["curlcmd", "curl", "999999"])

    from curlcommander.config import APP_DIR  # noqa: F401

    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1


def test_main_url_named_like_subcommand(monkeypatch, tmp_path):
    """A real URL whose path is 'curl' must not be treated as the subcommand."""
    monkeypatch.setattr(sys, "argv", ["curlcmd", "https://x/curl", "--curl-only"])
    # Should reach run_cli via the request parser and exit 0 (curl-only prints).
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 0


def test_module_entry_point_version():
    """`python -m curlcommander --version` is the frozen-binary entry path."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "curlcommander", "--version"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0
    assert "curlcmd" in out.stdout
