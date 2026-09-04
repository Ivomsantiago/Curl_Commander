"""Regression tests for Phase 1.8/1.9/1.10 — response bytes, truncation, pretty."""

import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.core.http_client import send
from curlcommander.core.request_model import RequestConfig
from curlcommander.core.response_formatter import charset_of, decode_body

# --- 1.8 binary integrity -------------------------------------------------


def test_charset_extraction():
    assert charset_of("text/html; charset=iso-8859-1") == "iso-8859-1"
    assert charset_of("application/json") is None


def test_decode_body_replaces_invalid_bytes():
    # Not valid UTF-8; must not raise, must not lose length catastrophically.
    assert decode_body(b"\xff\xfe\x00", "application/octet-stream")


@respx.mock
async def test_response_content_holds_raw_bytes():
    png = b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff"
    respx.get("https://x/img.png").mock(
        return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
    )
    result = await send(RequestConfig(method="GET", url="https://x/img.png"))
    assert result.content == png


def _args(**over):
    base = dict(
        subcommand=None,
        url="https://x/y",
        method="GET",
        headers=[],
        params=[],
        body="",
        body_file=None,
        json_body=None,
        form_body=None,
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
        curl_only=False,
        save=False,
        gui=False,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


@respx.mock
def test_output_writes_raw_bytes_not_formatted_text(tmp_path):
    png = b"\x89PNG\r\n\x1a\n\xde\xad\xbe\xef"
    respx.get("https://x/img.png").mock(
        return_value=httpx.Response(200, content=png, headers={"content-type": "image/png"})
    )
    out = tmp_path / "out.png"
    runner.run_cli(_args(url="https://x/img.png", output=str(out)))
    assert out.read_bytes() == png  # byte-for-byte, no utf-8 corruption


@respx.mock
def test_large_body_still_saves_full_to_output(tmp_path):
    big = "A" * (runner.DISPLAY_LIMIT_BYTES + 500)
    respx.get("https://x/big").mock(return_value=httpx.Response(200, text=big, headers={"content-type": "text/plain"}))
    out = tmp_path / "big.txt"
    runner.run_cli(_args(url="https://x/big", output=str(out)))
    assert len(out.read_text()) == len(big)
