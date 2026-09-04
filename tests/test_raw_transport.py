"""Tests for 2B.1/2B.2 — byte-faithful raw transport, no-default-headers."""

import socket
import threading

import httpx
import respx

from curlcommander.core.http_client import send
from curlcommander.core.raw_transport import (
    parse_raw_response,
    send_raw_request,
    serialize_request,
    target_from_url,
)
from curlcommander.core.request_model import RequestConfig

_RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/plain\r\n\r\nhi"


class _RecordingServer:
    """Single-shot TCP server that records the exact bytes received."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.host, self.port = self.sock.getsockname()
        self.received = b""
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.sock.accept()
        with conn:
            conn.settimeout(2.0)
            data = b""
            try:
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except TimeoutError:
                pass
            self.received = data
            conn.sendall(_RESPONSE)

    def close(self):
        self.sock.close()


def test_serialize_preserves_unnormalized_path():
    cfg = RequestConfig(method="GET", url="http://target/a/../../etc/passwd")
    raw = serialize_request(cfg)
    assert raw.split(b"\r\n")[0] == b"GET /a/../../etc/passwd HTTP/1.1"


def test_serialize_preserves_duplicate_headers_order_case():
    cfg = RequestConfig(
        method="GET",
        url="http://target/x",
        headers=[("X-Forwarded-For", "1.1.1.1"), ("X-Forwarded-For", "2.2.2.2"), ("host", "evil")],
    )
    raw = serialize_request(cfg).decode()
    assert "X-Forwarded-For: 1.1.1.1\r\n" in raw
    assert "X-Forwarded-For: 2.2.2.2\r\n" in raw
    assert "host: evil\r\n" in raw  # user-supplied Host wins, lowercase preserved


def test_byte_sent_is_byte_typed():
    server = _RecordingServer()
    try:
        cfg = RequestConfig(method="GET", url=f"http://127.0.0.1:{server.port}/a/../%2e%2e/passwd")
        raw = serialize_request(cfg)
        result = send_raw_request(raw, server.host, server.port, use_tls=False, timeout=2.0)
        server.thread.join(timeout=2)
    finally:
        server.close()
    assert server.received.startswith(b"GET /a/../%2e%2e/passwd HTTP/1.1\r\n")
    assert result.status_code == 200
    assert result.body == "hi"


def test_manual_cl_te_both_survive():
    """CL.TE smuggling primitive: both headers must reach the wire untouched."""
    server = _RecordingServer()
    try:
        raw = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 6\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nG"
        send_raw_request(raw, server.host, server.port, use_tls=False, timeout=2.0)
        server.thread.join(timeout=2)
    finally:
        server.close()
    got = server.received
    assert b"Content-Length: 6\r\n" in got
    assert b"Transfer-Encoding: chunked\r\n" in got


def test_target_from_url():
    assert target_from_url("https://x.com/y") == ("x.com", 443, True)
    assert target_from_url("http://x.com:8080/y") == ("x.com", 8080, False)
    assert target_from_url("host.only") == ("host.only", 443, True)


def test_parse_raw_response():
    status, reason, headers, body = parse_raw_response(_RESPONSE)
    assert status == 200 and reason == "OK"
    assert headers.get("Content-Type") == "text/plain"
    assert body == b"hi"


@respx.mock
async def test_no_default_headers_strips_user_agent():
    route = respx.get("https://x/y").mock(return_value=httpx.Response(200, text="ok"))
    cfg = RequestConfig(method="GET", url="https://x/y", no_default_headers=True)
    await send(cfg)
    sent = route.calls.last.request
    assert "user-agent" not in {k.lower() for k in sent.headers}
