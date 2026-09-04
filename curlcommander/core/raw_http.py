"""Parse a raw HTTP request block (Burp Repeater / .http files) into a config.

The request-line + headers + body are read as-is. The absolute URL is built
from an explicit ``--host`` override when given, otherwise from the Host header
(defaulting to https). Header order and duplicates are preserved.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import parse_header
from curlcommander.core.request_model import RequestConfig


class RawRequestError(ValueError):
    """Raised when a raw HTTP request block cannot be parsed."""


def parse_raw_request(text: str, host: str | None = None) -> RequestConfig:
    # Normalise line endings but keep the body's internal bytes intact.
    normalised = text.replace("\r\n", "\n")
    if "\n\n" in normalised:
        head, _, body = normalised.partition("\n\n")
    else:
        head, body = normalised, ""

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

    body = body if body.strip("\n") else ""
    body_type = "raw" if body else "none"

    return RequestConfig(
        method=method.upper(),
        url=url,
        headers=headers,
        body=body,
        body_type=body_type,
    )


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
