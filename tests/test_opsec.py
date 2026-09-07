"""Tests for 2B.8 — scope allowlist, dry-run, evidence capture."""

import json
import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.core import scope
from curlcommander.core.evidence import compose_raw_response, save_evidence
from curlcommander.core.request_model import RequestConfig, ResponseResult

# --- scope unit -----------------------------------------------------------


def test_scope_exact_wildcard_and_cidr():
    entries = ["api.target.com", "*.staging.target.com", "10.0.0.0/24"]
    assert scope.url_in_scope("https://api.target.com/x", entries)
    assert scope.url_in_scope("https://a.staging.target.com", entries)
    assert scope.url_in_scope("http://10.0.0.5:8080", entries)
    assert not scope.url_in_scope("https://evil.com", entries)
    assert not scope.url_in_scope("http://10.0.1.5", entries)


def test_scope_enforce_raises():
    with pytest.raises(scope.ScopeError):
        scope.enforce("https://prod.example.com", ["only.allowed.com"])


def test_scope_deny_excludes_host_covered_by_wildcard_allow():
    entries = ["*.karwei.nl", "!horrenconfigurator.karwei.nl"]
    assert scope.url_in_scope("https://other.karwei.nl", entries)
    assert not scope.url_in_scope("https://horrenconfigurator.karwei.nl/x", entries)


def test_scope_deny_wins_regardless_of_order_in_file():
    # Deny listed before the allow that would otherwise cover it.
    entries_deny_first = ["!horrenconfigurator.karwei.nl", "*.karwei.nl"]
    entries_deny_last = ["*.karwei.nl", "!horrenconfigurator.karwei.nl"]
    for entries in (entries_deny_first, entries_deny_last):
        assert not scope.host_in_scope("horrenconfigurator.karwei.nl", entries)
        assert scope.host_in_scope("other.karwei.nl", entries)


def test_scope_deny_wins_even_with_exact_allow_entry():
    # Even an explicit exact-host allow entry loses to a deny for that host.
    entries = ["horrenconfigurator.karwei.nl", "!horrenconfigurator.karwei.nl"]
    assert not scope.host_in_scope("horrenconfigurator.karwei.nl", entries)


def test_scope_enforce_deny_message_distinguishes_exclusion():
    entries = ["*.karwei.nl", "!horrenconfigurator.karwei.nl"]
    with pytest.raises(scope.ScopeError, match="excluded"):
        scope.enforce("https://horrenconfigurator.karwei.nl/panel", entries)


def test_load_scope_parses_allow_and_deny_lines(tmp_path):
    scopefile = tmp_path / "scope.txt"
    scopefile.write_text(
        "# comment\n*.karwei.nl\n!horrenconfigurator.karwei.nl\n\napi.target.com\n",
        encoding="utf-8",
    )
    entries = scope.load_scope(scopefile)
    assert entries == ["*.karwei.nl", "!horrenconfigurator.karwei.nl", "api.target.com"]
    assert scope.url_in_scope("https://other.karwei.nl", entries)
    assert not scope.url_in_scope("https://horrenconfigurator.karwei.nl", entries)
    assert scope.url_in_scope("https://api.target.com", entries)


def test_scope_without_bang_lines_is_unchanged():
    """No '!' entries -> deny list empty -> behaviour identical to before."""
    entries = ["api.target.com", "*.staging.target.com", "10.0.0.0/24"]
    assert scope.url_in_scope("https://api.target.com/x", entries)
    assert scope.url_in_scope("https://a.staging.target.com", entries)
    assert scope.url_in_scope("http://10.0.0.5:8080", entries)
    assert not scope.url_in_scope("https://evil.com", entries)


# --- evidence unit --------------------------------------------------------


def test_save_evidence_writes_files(tmp_path):
    cfg = RequestConfig(method="GET", url="https://api.target.com/x")
    result = ResponseResult(200, "OK", {"content-type": "text/plain"}, "hi", "text/plain", 12.0, 2, None)
    folder = save_evidence(
        tmp_path,
        cfg,
        b"GET /x HTTP/1.1\r\n\r\n",
        compose_raw_response(result),
        result,
        engagement="ENG-42",
    )
    assert (folder / "request.txt").read_bytes().startswith(b"GET /x")
    assert b"hi" in (folder / "response.txt").read_bytes()
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["engagement"] == "ENG-42" and meta["status_code"] == 200


# --- CLI integration ------------------------------------------------------


def _args(**over):
    base = dict(
        subcommand=None,
        url="https://api.target.com/x",
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
        fuzz_mode="clusterbomb",
        encode=None,
        concurrency=10,
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
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


@respx.mock
def test_cli_out_of_scope_refused_and_not_sent(tmp_path):
    route = respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    scopefile = tmp_path / "scope.txt"
    scopefile.write_text("only.allowed.com\n")
    rc = runner.run_cli(_args(scope=str(scopefile)))
    assert rc == runner.EXIT_USAGE
    assert len(route.calls) == 0  # never fired


@respx.mock
def test_cli_dry_run_does_not_send(tmp_path):
    route = respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    rc = runner.run_cli(_args(dry_run=True))
    assert rc == runner.EXIT_OK
    assert len(route.calls) == 0


@respx.mock
def test_cli_evidence_saved(tmp_path):
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    evdir = tmp_path / "evidence"
    runner.run_cli(_args(evidence=str(evdir), engagement="ENG-7"))
    saved = list(evdir.rglob("meta.json"))
    assert saved
    assert json.loads(saved[0].read_text())["engagement"] == "ENG-7"


@respx.mock
def test_cli_burp_shortcut_sets_proxy_and_no_verify(monkeypatch):
    import curlcommander.cli.runner as r

    captured = {}

    async def fake_send(config):
        captured["proxy"] = config.proxy
        captured["verify"] = config.verify_ssl
        from curlcommander.core.request_model import ResponseResult

        return ResponseResult(200, "OK", {}, "ok", "text/plain", 1.0, 2, None)

    monkeypatch.setattr(r, "send", fake_send)
    r.run_cli(_args(url="https://api.target.com/x", burp=True))
    assert captured["proxy"] == "http://127.0.0.1:8080"
    assert captured["verify"] is False
