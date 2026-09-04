"""Regression tests for Phase 1.6 — meaningful process exit codes."""

import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.cli.arg_parser import build_request_parser


def _args(**over):
    """A namespace mirroring the request parser defaults, overridable."""
    base = dict(
        subcommand=None, url="https://x/y", method="GET", headers=[], params=[],
        body="", body_file=None, json_body=None, form_body=None,
        auth_bearer=None, auth_basic=None, auth_apikey=None, proxy=None,
        retry=0, retry_delay=0.0, compressed=False, http2=False, output="",
        pretty=False, env_file=None, no_redirect=False, no_verify=False,
        timeout=30.0, fail=False, curl_only=False, save=False, gui=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


@respx.mock
def test_success_returns_zero():
    respx.get("https://x/y").mock(return_value=httpx.Response(200, text="ok"))
    assert runner.run_cli(_args()) == runner.EXIT_OK


@respx.mock
def test_network_error_returns_two():
    respx.get("https://x/y").mock(side_effect=httpx.ConnectError("boom"))
    assert runner.run_cli(_args()) == runner.EXIT_NETWORK


@respx.mock
def test_http_error_without_fail_is_zero():
    respx.get("https://x/y").mock(return_value=httpx.Response(500, text="err"))
    assert runner.run_cli(_args()) == runner.EXIT_OK


@respx.mock
def test_http_error_with_fail_returns_22():
    respx.get("https://x/y").mock(return_value=httpx.Response(404, text="nope"))
    assert runner.run_cli(_args(fail=True)) == runner.EXIT_HTTP


def test_missing_history_id_returns_usage():
    assert runner.run_cli(_args(subcommand="replay", id=999999)) == runner.EXIT_USAGE


def test_argparse_usage_error_exits_1():
    parser = build_request_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--not-a-flag"])
    assert exc.value.code == 1
