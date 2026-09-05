"""Parse a raw HTTP request block (Burp Repeater / .http files) into a config.

The request-line + headers are parsed; the body is kept byte-for-byte. The
absolute URL is built from an explicit ``--host`` override when given, otherwise
from the Host header (defaulting to https). Header order and duplicates are
preserved.

Newline handling is deliberate: ``\\r\\n`` is normalised only inside the
request-line + header block so header parsing is portable, **never** inside the
body --- a hand-crafted ``Transfer-Encoding: chunked`` body or a CL.TE payload
must reach the wire with its exact framing (that is the whole point of the raw
path, and it is what broke on Windows text reads).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import parse_header
from curlcommander.core.request_model import RequestConfig


class RawRequestError(ValueError):
    """Raised when a raw HTTP request block cannot be parsed."""


def parse_raw_request_bytes(data: bytes, host: str | None = None) -> RequestConfig:
    """Parse a raw request from bytes, preserving the body verbatim.

    Body bytes are carried through ``config.body`` as latin-1 (a 1:1 byte
    mapping), so no byte is lost or newline-translated.
    """
    # Split head from body on the first blank line, honouring CRLF or LF, in
    # BYTES so the body is never touched.
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = data.find(sep)
        if idx != -1:
            head_bytes = data[:idx]
            body_bytes = data[idx + len(sep) :]
            break
    else:
        head_bytes, body_bytes = data, b""

    # Only the head is newline-normalised and decoded for parsing.
    head = head_bytes.replace(b"\r\n", b"\n").decode("latin-1")
    lines = head.split("\n")
    if not lines or not lines[0].strip():
        raise RawRequestError("empty request line")

    request_line = lines[0].strip()
    parts = request_line.split()
    if len(parts) < 2:
        raise RawRequestError(f"malformed request line: {request_line!r}")
    method, target = parts[0], parts[1]

    headers = HeaderList()
    for line in lines[1:]:
        if not line.strip():
            continue
        try:
            k, v = parse_header(line)
            headers.append(k, v)
        except ValueError:
            continue

    host_header = headers.get("Host")
    url = _build_url(target, host, host_header)

    body = body_bytes.decode("latin-1")  # 1:1 byte mapping, exact
    body_type = "raw" if body else "none"

    return RequestConfig(
        method=method.upper(),
        url=url,
        headers=headers,
        body=body,
        body_type=body_type,
    )


def parse_raw_request(text: str, host: str | None = None) -> RequestConfig:
    """Text convenience wrapper around :func:`parse_raw_request_bytes`."""
    return parse_raw_request_bytes(text.encode("latin-1", errors="replace"), host)


def _build_url(target: str, host_override: str | None, host_header: str | None) -> str:
    if target.startswith(("http://", "https://")):
        return target

    if host_override:
        split = urlsplit(host_override if "://" in host_override else f"https://{host_override}")
        scheme = split.scheme or "https"
        authority = split.netloc or split.path
        return f"{scheme}://{authority}{target}"

    if host_header:
        return f"https://{host_header}{target}"

    raise RawRequestError("no Host header and no --host override; cannot build URL")
