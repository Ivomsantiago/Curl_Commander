"""Convert between a RequestConfig and an editable raw-HTTP text (GUI helper).

The Repeater and Intruder tabs let the user edit a request as free raw text.
Rendering reuses the byte-faithful serialiser; parsing reuses the raw-request
parser — no new request logic here.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from curlcommander.core.raw_http import parse_raw_request_bytes
from curlcommander.core.raw_transport import serialize_request
from curlcommander.core.request_model import RequestConfig


def config_to_text(config: RequestConfig) -> str:
    """A raw HTTP/1.1 request as editable text (request line + headers + body)."""
    return serialize_request(config).decode("latin-1")


def base_url_of(url: str) -> str:
    """The scheme://host[:port] of a URL, used to rebuild a config from text."""
    split = urlsplit(url)
    return urlunsplit((split.scheme or "https", split.netloc, "", "", ""))


def text_to_config(text: str, base_url: str) -> RequestConfig:
    """Parse edited raw text back into a config, keeping the original host/scheme."""
    return parse_raw_request_bytes(text.encode("latin-1", errors="replace"), host=base_url)
