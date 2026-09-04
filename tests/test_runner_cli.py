"""Broad CLI runner coverage: subcommands and dispatch paths."""

import types

import httpx
import pytest
import respx

from curlcommander.cli import runner


def _args(**over):
    base = dict(
        subcommand=None,
        url=None,
        method="GET",
        headers=[],
        params=[],
        cookies=[],
        cookie_jar=None,
        session=None,
        form=[],
        body="",
        body_file=None,
        json_body=None,
        form_body=None,
        import_curl=None,
        import_file=None,
        import_clipboard=False,
        import_raw=None,
        host=None,
        raw_request=None,
        raw_path=False,
        no_default_headers=False,
        graphql=None,
        graphql_vars=None,
        graphql_introspection=False,
        xml=None,
        soap=None,
        soap_action=None,
        soap_envelope=False,
        grpc_web=False,
        stream=False,
        wordlists=[],
        payloads=[],
        fuzz_mode="clusterbomb",
        encode=None,
        concurrency=5,
        rate=0.0,
        mc=None,
        fc=None,
        ms=None,
        fs=None,
        mr=None,
        auth_bearer=None,
        auth_basic=None,
        auth_apikey=None,
        proxy=None,
        retry=0,
        retry_delay=0.0,
        compressed=False,
        http2=False,
        output="",
        pretty=False,
        raw=False,
        env_file=None,
        no_redirect=False,
        no_verify=False,
        timeout=30.0,
        fail=False,
        no_redact=False,
        curl_only=False,
        save=False,
        gui=False,
        assert_status=None,
        assert_headers=[],
        assert_body=[],
        assert_jsonpath=[],
        assert_max_ms=None,
        report=None,
        scope=None,
        dry_run=False,
        evidence=None,
        engagement=None,
        log_file=None,
        log_level=None,
        reveal=False,
        id=None,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


def test_history_empty():
    assert runner.run_cli(_args(subcommand="history")) == runner.EXIT_OK


def test_clear_history():
    assert runner.run_cli(_args(subcommand="clear-history")) == runner.EXIT_OK


@respx.mock
def test_full_subcommand_lifecycle(tmp_path):
    respx.get("https://x/y").mock(return_value=httpx.Response(200, json={"ok": True}))
    # send + save
    assert runner.run_cli(_args(url="https://x/y")) == runner.EXIT_OK
    # list, show curl, export, delete
    assert runner.run_cli(_args(subcommand="history")) == runner.EXIT_OK
    assert runner.run_cli(_args(subcommand="history", reveal=True)) == runner.EXIT_OK
    assert runner.run_cli(_args(subcommand="curl", id=1)) == runner.EXIT_OK
    assert runner.run_cli(_args(subcommand="curl", id=1, reveal=True)) == runner.EXIT_OK
    out = tmp_path / "e.json"
    assert runner.run_cli(_args(subcommand="export-history", output=str(out))) == runner.EXIT_OK
    assert out.exists()
    assert runner.run_cli(_args(subcommand="delete-history", id=1)) == runner.EXIT_OK
    assert runner.run_cli(_args(subcommand="delete-history", id=1)) == runner.EXIT_USAGE


def test_curl_only_prints_and_saves():
    assert runner.run_cli(_args(url="https://x/y", curl_only=True, save=True)) == runner.EXIT_OK


@respx.mock
def test_cli_import_curl_then_send():
    respx.post("https://api.x/y").mock(return_value=httpx.Response(201, text="ok"))
    cmd = "curl -X POST https://api.x/y -H 'Content-Type: application/json' --data-raw '{}'"
    assert runner.run_cli(_args(import_curl=cmd)) == runner.EXIT_OK


@respx.mock
def test_cli_graphql_introspection():
    respx.post("https://x/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"__schema": {"types": [{"name": "Q"}]}}})
    )
    assert runner.run_cli(_args(url="https://x/graphql", graphql_introspection=True)) == runner.EXIT_OK


@respx.mock
def test_cli_stream():
    respx.get("https://x/s").mock(return_value=httpx.Response(200, text="a\nb"))
    assert runner.run_cli(_args(url="https://x/s", stream=True)) == runner.EXIT_OK


@respx.mock
def test_cli_fuzz_with_payloads():
    respx.get(url__regex=r"https://x/.*").mock(return_value=httpx.Response(200, text="x"))
    rc = runner.run_cli(_args(url="https://x/FUZZ", payloads=["traversal"], concurrency=3))
    assert rc == runner.EXIT_OK


def test_cli_fuzz_without_marker_is_usage(tmp_path):
    wl = tmp_path / "w.txt"
    wl.write_text("a\nb\n")
    assert runner.run_cli(_args(url="https://x/y", wordlists=[str(wl)])) == runner.EXIT_USAGE


@respx.mock
def test_cli_assertion_report_json(capsys):
    respx.get("https://x/y").mock(return_value=httpx.Response(200, json={"ok": True}))
    rc = runner.run_cli(_args(url="https://x/y", assert_status=200, report="json"))
    assert rc == runner.EXIT_OK
    assert '"passed": true' in capsys.readouterr().out
