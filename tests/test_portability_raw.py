"""F1.1 regression: raw request byte-fidelity from a file (Linux and Windows).

The fixture is written with explicit \\r\\n bytes; the test asserts the exact
bytes reach the socket, so it catches the Windows universal-newline collapse
that used to destroy chunked / CL.TE framing.
"""

import socket
import threading
import types

import pytest

from curlcommander.cli import runner
from curlcommander.core.raw_http import parse_raw_request_bytes
from curlcommander.core.raw_transport import fix_content_length, is_smuggling_shaped

# A chunked body with hand-written sizes, CRLF framing in literal bytes.
CHUNKED = (
    b"POST /x HTTP/1.1\r\nHost: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n"
)

CL_TE = b"POST / HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 6\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\nG"


class _RecordingServer:
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
            conn.settimeout(0.4)  # short read-idle, then respond promptly
            data = b""
            try:
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except (TimeoutError, OSError):
                pass
            self.received = data
            try:
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nhi")
            except OSError:
                pass

    def close(self):
        self.sock.close()


def _args(path, **over):
    base = dict(
        subcommand=None,
        raw_request=str(path),
        host=None,
        no_fix_length=False,
        no_verify=False,
        timeout=2.0,
        scope=None,
        dry_run=False,
        log_file=None,
        log_level=None,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def _write_binary(tmp_path, name, data: bytes):
    p = tmp_path / name
    p.write_bytes(data)  # never write_text: keep the CRLF bytes intact
    return p


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


def test_chunked_body_reaches_socket_identical(tmp_path, monkeypatch):
    f = _write_binary(tmp_path, "chunked.txt", CHUNKED)
    server = _RecordingServer()
    monkeypatch.setattr(runner, "_target_from_raw", lambda raw: (server.host, server.port, False))
    try:
        rc = runner.run_cli(_args(f))
        server.thread.join(timeout=2)
    finally:
        server.close()
    assert rc == runner.EXIT_OK
    # Byte-for-byte: chunk sizes, CRLFs and terminator are all intact.
    assert server.received == CHUNKED


def test_cl_te_both_headers_survive(tmp_path, monkeypatch):
    f = _write_binary(tmp_path, "clte.txt", CL_TE)
    server = _RecordingServer()
    monkeypatch.setattr(runner, "_target_from_raw", lambda raw: (server.host, server.port, False))
    try:
        runner.run_cli(_args(f))
        server.thread.join(timeout=2)
    finally:
        server.close()
    assert server.received == CL_TE  # not "fixed" — smuggling shape detected


def test_smuggling_detection_and_length_fix():
    assert is_smuggling_shaped(CHUNKED)
    assert is_smuggling_shaped(CL_TE)
    # A plain request with a wrong Content-Length is safe to fix.
    plain = b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 99\r\n\r\nhello"
    assert not is_smuggling_shaped(plain)
    fixed = fix_content_length(plain)
    assert b"Content-Length: 5\r\n" in fixed
    assert fixed.endswith(b"\r\n\r\nhello")


def test_parse_raw_request_bytes_preserves_body():
    cfg = parse_raw_request_bytes(CHUNKED)
    # Body kept byte-for-byte (latin-1 1:1), CRLFs intact.
    assert cfg.body.encode("latin-1") == b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n"
