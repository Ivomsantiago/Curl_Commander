"""Byte-faithful HTTP over a raw socket, bypassing httpx normalisation.

httpx rewrites the request line (``/a/../b`` -> ``/b``), reorders/《normalises》
headers, and manages Content-Length/Transfer-Encoding itself --- fine for normal
use, fatal for request-smuggling, CRLF, and path-traversal testing. This module
writes exactly the bytes given onto the wire (TLS for https) and returns exactly
the bytes received, so the byte sent is the byte typed.
"""

from __future__ import annotations

import socket
import ssl
import time
from urllib.parse import urlsplit

from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig, ResponseResult


class RawTransportError(RuntimeError):
    pass


def target_from_url(url: str) -> tuple[str, int, bool]:
    """Return (host, port, use_tls) from a URL or host[:port] string."""
    if "://" not in url:
        url = "https://" + url
    split = urlsplit(url)
    if not split.hostname:
        raise RawTransportError(f"cannot determine host from {url!r}")
    use_tls = split.scheme == "https"
    port = split.port or (443 if use_tls else 80)
    return split.hostname, port, use_tls


def serialize_request(config: RequestConfig, no_default_headers: bool = False) -> bytes:
    """Serialise a config to raw HTTP/1.1 bytes without any normalisation.

    The path and query are taken verbatim from the URL so traversal/encoding
    payloads survive. Header order, case and duplicates are preserved.
    """
    split = urlsplit(config.url)
    path = split.path or "/"
    if split.query:
        path = f"{path}?{split.query}"

    lines = [f"{config.method} {path} HTTP/1.1"]

    headers = HeaderList(config.headers)
    if "host" not in headers and split.hostname:
        host = split.hostname
        if split.port:
            host = f"{host}:{split.port}"
        lines.append(f"Host: {host}")

    if not no_default_headers:
        headers.setdefault("Connection", "close")
    body_bytes = config.body.encode() if config.body else b""
    if body_bytes and "content-length" not in headers and "transfer-encoding" not in headers:
        headers.setdefault("Content-Length", str(len(body_bytes)))

    if config.cookies:
        headers.append("Cookie", "; ".join(f"{k}={v}" for k, v in config.cookies))

    for key, value in headers:
        lines.append(f"{key}: {value}")

    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("latin-1", errors="replace") + body_bytes


def _split_head_body(raw: bytes) -> tuple[bytes, bytes, bytes]:
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(sep)
        if idx != -1:
            return raw[:idx], sep, raw[idx + len(sep) :]
    return raw, b"", b""


def is_smuggling_shaped(raw: bytes) -> bool:
    """True if the request looks like a deliberate smuggling/desync payload.

    Chunked transfer-encoding, or more than one Content-Length, or both a
    Content-Length and a Transfer-Encoding present. Such requests must never be
    "helpfully" rewritten --- their broken framing is the test.
    """
    head, _, _ = _split_head_body(raw)
    lowered = head.replace(b"\r\n", b"\n").lower()
    has_te = b"\ntransfer-encoding:" in b"\n" + lowered
    cl_count = (b"\n" + lowered).count(b"\ncontent-length:")
    return has_te or cl_count > 1


def fix_content_length(raw: bytes) -> bytes:
    """Recompute a single Content-Length header to match the actual body.

    Only touches a lone existing Content-Length; leaves everything else byte
    for byte. Callers must gate this behind :func:`is_smuggling_shaped`.
    """
    head, sep, body = _split_head_body(raw)
    if not sep:
        return raw
    newline = b"\r\n" if b"\r\n" in head else b"\n"
    lines = head.split(newline)
    out = []
    replaced = False
    for line in lines:
        if line[:15].lower() == b"content-length:" and not replaced:
            out.append(b"Content-Length: " + str(len(body)).encode())
            replaced = True
        else:
            out.append(line)
    if not replaced:
        return raw
    return newline.join(out) + sep + body


def send_raw(
    raw: bytes,
    host: str,
    port: int,
    use_tls: bool,
    verify_ssl: bool = True,
    timeout: float = 30.0,
) -> tuple[bytes, float]:
    """Send raw bytes and read the raw response. Returns (bytes, elapsed_ms)."""
    start = time.perf_counter()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise RawTransportError(f"connection failed: {exc}") from exc

    try:
        if use_tls:
            ctx = ssl.create_default_context()
            if not verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=host)

        sock.sendall(raw)
        sock.settimeout(timeout)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        try:
            sock.close()
        except OSError:
            pass

    elapsed_ms = (time.perf_counter() - start) * 1000
    return b"".join(chunks), elapsed_ms


def parse_raw_response(data: bytes) -> tuple[int | None, str, HeaderList, bytes]:
    """Best-effort parse of a raw HTTP response into status/headers/body."""
    if not data:
        return None, "", HeaderList(), b""
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status: int | None = None
    reason = ""
    if lines:
        parts = lines[0].split(b" ", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            status = int(parts[1])
        if len(parts) >= 3:
            reason = parts[2].decode("latin-1", errors="replace")
    headers = HeaderList()
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            headers.append(k.decode("latin-1").strip(), v.decode("latin-1").strip())
    return status, reason, headers, body


def send_raw_request(
    raw: bytes,
    host: str,
    port: int,
    use_tls: bool,
    verify_ssl: bool = True,
    timeout: float = 30.0,
) -> ResponseResult:
    """High-level: send raw bytes, parse the response into a ResponseResult."""
    data, elapsed_ms = send_raw(raw, host, port, use_tls, verify_ssl, timeout)
    status, reason, headers, body = parse_raw_response(data)
    content_type = headers.get("content-type", "") or ""
    return ResponseResult(
        status_code=status,
        reason=reason,
        headers=headers.to_dict(),
        body=body.decode("utf-8", errors="replace"),
        content_type=content_type,
        duration_ms=elapsed_ms,
        size_bytes=len(body),
        error=None if data else "no data received",
        content=data,  # full raw bytes (status line + headers + body)
    )
