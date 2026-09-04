"""Regression tests for Phase 1.4/1.5 — secret redaction and lossless replay."""

import json
import sqlite3
import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.core.redaction import REDACTED, redact_config, reveal_config
from curlcommander.core.request_model import RequestConfig


# --- unit: redact_config --------------------------------------------------

def test_bearer_without_env_is_redacted():
    cfg = RequestConfig(method="GET", url="https://x", auth_type="bearer", auth_value="s3cr3t-token")
    red = redact_config(cfg, {})
    assert red.auth_value == REDACTED
    assert red.auth_type == "bearer"  # type preserved for replay


def test_bearer_from_env_becomes_reference():
    cfg = RequestConfig(method="GET", url="https://x", auth_type="bearer", auth_value="abc123")
    red = redact_config(cfg, {"API_TOKEN": "abc123"})
    assert red.auth_value == "{{API_TOKEN}}"


def test_apikey_keeps_header_name_masks_value():
    cfg = RequestConfig(method="GET", url="https://x", auth_type="apikey", auth_value="X-API-Key: supersecret")
    red = redact_config(cfg, {})
    assert red.auth_value == f"X-API-Key: {REDACTED}"


def test_sensitive_headers_masked_others_untouched():
    cfg = RequestConfig(
        method="GET", url="https://x",
        headers=[("Authorization", "Bearer tok"), ("Cookie", "sid=deadbeef"), ("Accept", "application/json")],
    )
    red = redact_config(cfg, {})
    assert red.headers.get("Authorization") == f"Bearer {REDACTED}"
    assert red.headers.get("Cookie") == REDACTED
    assert red.headers.get("Accept") == "application/json"


def test_proxy_credentials_redacted():
    cfg = RequestConfig(method="GET", url="https://x", proxy="http://user:pass@127.0.0.1:8080")
    red = redact_config(cfg, {})
    assert "pass" not in red.proxy
    assert REDACTED in red.proxy
    assert "127.0.0.1:8080" in red.proxy


def test_reveal_round_trip():
    cfg = RequestConfig(method="GET", url="https://x", auth_type="bearer", auth_value="tok")
    red = redact_config(cfg, {"T": "tok"})
    assert red.auth_value == "{{T}}"
    assert reveal_config(red, {"T": "tok"}).auth_value == "tok"


# --- integration: nothing secret reaches disk -----------------------------

def _args(**over):
    base = dict(
        subcommand=None, url="https://api/me", method="GET", headers=[], params=[],
        body="", body_file=None, json_body=None, form_body=None,
        auth_bearer=None, auth_basic=None, auth_apikey=None, proxy=None,
        retry=0, retry_delay=0.0, compressed=False, http2=False, output="",
        pretty=False, raw=False, env_file=None, no_redirect=False, no_verify=False,
        timeout=30.0, fail=False, no_redact=False, curl_only=False, save=False, gui=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@respx.mock
def test_secret_never_reaches_sqlite_or_export(tmp_path, monkeypatch):
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", db)
    respx.get("https://api/me").mock(return_value=httpx.Response(200, text="ok"))

    secret = "TOPSECRET_TOKEN_9000"
    runner.run_cli(_args(auth_bearer=secret))

    raw = db.read_bytes()
    assert secret.encode() not in raw  # not in curl_cmd, not in config_json, not anywhere

    out = tmp_path / "export.json"
    runner.run_cli(_args(subcommand="export-history", output=str(out), reveal=False))
    assert secret not in out.read_text()


@respx.mock
def test_replay_resolves_env_reference(tmp_path, monkeypatch):
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", db)
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=live-value-42\n")
    route = respx.get("https://api/me").mock(return_value=httpx.Response(200, text="ok"))

    # Save: token comes from env-file -> stored as {{TOKEN}}, not the literal.
    runner.run_cli(_args(auth_bearer="{{TOKEN}}", env_file=str(env_file)))
    assert route.calls.last.request.headers["authorization"] == "Bearer live-value-42"

    # Replay with TOKEN present in the environment -> real credential is sent.
    monkeypatch.setenv("TOKEN", "live-value-42")
    assert runner.run_cli(_args(subcommand="replay", id=1)) == runner.EXIT_OK
    assert route.calls.last.request.headers["authorization"] == "Bearer live-value-42"


@respx.mock
def test_replay_of_redacted_literal_fails_without_sending(tmp_path, monkeypatch):
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", db)
    route = respx.get("https://api/me").mock(return_value=httpx.Response(200, text="ok"))

    runner.run_cli(_args(auth_bearer="literal-secret"))  # no env -> stored REDACTED
    calls_before = len(route.calls)

    rc = runner.run_cli(_args(subcommand="replay", id=1))
    assert rc == runner.EXIT_USAGE
    assert len(route.calls) == calls_before  # nothing was sent (no empty credential)
