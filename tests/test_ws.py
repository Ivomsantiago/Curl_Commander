"""Tests for the WebSocket transport + fuzzer seam (item 5)."""

import asyncio

import pytest

from curlcommander.core.fuzzer import FuzzFilters, run_fuzz
from curlcommander.core.request_model import RequestConfig, ResponseResult

# --- the fuzzer's Transport seam (no websockets dependency needed) --------


async def _fake_transport(cfg: RequestConfig) -> ResponseResult:
    # Echo the body length back as a synthetic reply; anything containing
    # "boom" reports an error, to exercise the error path.
    if "boom" in cfg.body:
        return ResponseResult(None, "WS", {}, "", "", 1.0, 0, "connection closed")
    body = f"reply:{cfg.body}"
    return ResponseResult(101, "WS", {}, body, "application/websocket", 1.0, len(body), None)


@pytest.mark.asyncio
async def test_run_fuzz_uses_injected_transport():
    template = RequestConfig(method="GET", url="wss://x", body='{"cmd":"FUZZ"}', body_type="raw")
    results = await run_fuzz(template, [["ping", "pong"]], concurrency=1, transport=_fake_transport)
    assert len(results) == 2
    assert all(r.status_code == 101 for r in results)
    replies = {r.payloads[0] for r in results}
    assert replies == {"ping", "pong"}


@pytest.mark.asyncio
async def test_run_fuzz_transport_error_survives_mid_fuzz():
    template = RequestConfig(method="GET", url="wss://x", body="FUZZ", body_type="raw")
    results = await run_fuzz(template, [["ok", "boom"]], concurrency=1, transport=_fake_transport)
    by_payload = {r.payloads[0]: r for r in results}
    assert by_payload["ok"].status_code == 101
    assert by_payload["boom"].status_code is None
    assert by_payload["boom"].error == "connection closed"


@pytest.mark.asyncio
async def test_run_fuzz_transport_filter_by_regex():
    template = RequestConfig(method="GET", url="wss://x", body="FUZZ", body_type="raw")
    filters = FuzzFilters(match_regex="reply:only")
    results = await run_fuzz(template, [["only", "other"]], concurrency=1, filters=filters, transport=_fake_transport)
    assert [r.payloads[0] for r in results] == ["only"]


# --- CLI runner dispatch with a fake client (no websockets needed) --------


class _FakeClient:
    def __init__(self, url, *, read_timeout=10.0, extra_headers=None):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    def transport(self):
        return _fake_transport


def _ws_args(**over):
    base = dict(
        subcommand="ws",
        ws_cmd="fuzz",
        url="ws://127.0.0.1:1234",
        message='{"cmd":"FUZZ"}',
        wordlists=[],
        ws_headers=[],
        scope=None,
        mode="clusterbomb",
        concurrency=1,
        rate=0.0,
        mc=None,
        fc=None,
        ms=None,
        fs=None,
        mr=None,
        timeout=5.0,
    )
    base.update(over)
    return __import__("types").SimpleNamespace(**base)


def test_run_ws_missing_dependency_degrades(monkeypatch, capsys):
    from curlcommander.cli import runner
    from curlcommander.core import ws_client

    monkeypatch.setattr(ws_client, "ws_available", lambda: False)
    code = runner._run_ws(_ws_args())
    assert code == runner.EXIT_USAGE
    assert "ws" in capsys.readouterr().out.lower()


def test_run_ws_fuzz_with_fake_client(monkeypatch, tmp_path, capsys):
    from curlcommander.cli import runner
    from curlcommander.core import ws_client

    wl = tmp_path / "w.txt"
    wl.write_text("a\nb\nc\n", encoding="utf-8")

    monkeypatch.setattr(ws_client, "ws_available", lambda: True)
    monkeypatch.setattr(ws_client, "WSClient", _FakeClient)
    code = runner._run_ws(_ws_args(wordlists=[str(wl)]))
    assert code == runner.EXIT_OK
    assert "WS fuzz results (3 shown)" in capsys.readouterr().out


def test_run_ws_fuzz_requires_marker(monkeypatch, capsys):
    from curlcommander.cli import runner
    from curlcommander.core import ws_client

    monkeypatch.setattr(ws_client, "ws_available", lambda: True)
    monkeypatch.setattr(ws_client, "WSClient", _FakeClient)
    code = runner._run_ws(_ws_args(message="no marker here"))
    assert code == runner.EXIT_USAGE
    assert "FUZZ" in capsys.readouterr().out


# --- WSClient against a real local server (needs the [ws] extra) ----------

websockets = pytest.importorskip("websockets")


@pytest.mark.asyncio
async def test_ws_client_send_and_fuzz_roundtrip():
    from curlcommander.core.ws_client import WSClient

    async def echo(conn):
        async for message in conn:
            await conn.send(f"echo:{message}")

    server = await websockets.serve(echo, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://127.0.0.1:{port}"
    try:
        async with WSClient(url, read_timeout=5.0) as client:
            one = await client.send_message("hello")
            assert one.status_code == 101
            assert one.body == "echo:hello"

            template = RequestConfig(method="GET", url=url, body="msg-FUZZ", body_type="raw")
            results = await run_fuzz(template, [["a", "b", "c"]], concurrency=1, transport=client.transport())
            assert len(results) == 3
            assert {r.size_bytes for r in results}  # all got a reply
            assert all(r.status_code == 101 for r in results)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_client_read_timeout_when_server_silent():
    from curlcommander.core.ws_client import WSClient

    async def silent(conn):
        await asyncio.sleep(5)  # never replies within the read window

    server = await websockets.serve(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        async with WSClient(f"ws://127.0.0.1:{port}", read_timeout=0.2) as client:
            result = await client.send_message("hi")
            assert result.status_code is None
            assert result.error and "timeout" in result.error
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_client_connect_failure_is_wserror():
    from curlcommander.core.ws_client import WSClient, WSError

    # Nothing listening on this port -> a clean WSError, not a raw traceback.
    with pytest.raises(WSError):
        async with WSClient("ws://127.0.0.1:9", read_timeout=0.5):
            pass
