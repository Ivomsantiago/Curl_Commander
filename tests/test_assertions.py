"""Tests for 2.6 assertions and reports."""

import json
import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.core.assertions import AssertionSpec, eval_jsonpath, format_report, run_assertions
from curlcommander.core.request_model import ResponseResult


def _result(status=200, body="", headers=None, ms=10.0):
    return ResponseResult(
        status_code=status,
        reason="OK",
        headers=headers or {},
        body=body,
        content_type="application/json",
        duration_ms=ms,
        size_bytes=len(body),
        error=None,
    )


def test_jsonpath_equality():
    r = eval_jsonpath('{"user":{"id":42}}', "$.user.id==42")
    assert r.passed


def test_jsonpath_array_index():
    r = eval_jsonpath('{"items":[{"n":1},{"n":2}]}', "$.items[1].n == 2")
    assert r.passed


def test_jsonpath_mismatch_fails():
    assert not eval_jsonpath('{"ok":false}', "$.ok==true").passed


def test_status_and_header_and_body():
    res = _result(status=200, body='{"ok":true}', headers={"x-frame-options": "DENY"})
    spec = AssertionSpec(status=200, headers=["X-Frame-Options: DENY"], body_contains=['"ok":true'])
    results = run_assertions(res, spec)
    assert all(r.passed for r in results)


def test_max_ms_fail():
    res = _result(ms=900)
    assert not run_assertions(res, AssertionSpec(max_ms=500))[0].passed


def test_report_json_and_junit():
    res = _result(status=500)
    results = run_assertions(res, AssertionSpec(status=200))
    j = json.loads(format_report(results, "json", url="https://x"))
    assert j["passed"] is False
    xml = format_report(results, "junit")
    assert "<testsuite" in xml and 'failures="1"' in xml


def _args(**over):
    base = dict(
        subcommand=None,
        url="https://x/y",
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
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


@respx.mock
def test_cli_assertion_pass_is_zero():
    respx.get("https://x/y").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert runner.run_cli(_args(assert_status=200, assert_jsonpath=["$.ok==true"])) == runner.EXIT_OK


@respx.mock
def test_cli_assertion_fail_is_three():
    respx.get("https://x/y").mock(return_value=httpx.Response(404, text="no"))
    assert runner.run_cli(_args(assert_status=200)) == runner.EXIT_ASSERT
