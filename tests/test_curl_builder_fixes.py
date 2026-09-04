"""Regression tests for Phase 1 curl-builder bugs (1.1, 1.2, 1.3)."""

import base64
import shlex

import httpx
import respx

from curlcommander.core.curl_builder import build_curl
from curlcommander.core.http_client import send
from curlcommander.core.request_model import RequestConfig


def _parts(cmd: str) -> list[str]:
    return shlex.split(cmd)


# --- 1.1 basic auth must appear in the generated curl ---------------------


def test_basic_auth_emits_dash_u():
    cfg = RequestConfig(method="POST", url="https://x/y", auth_type="basic", auth_value="admin:s3cr3t")
    parts = _parts(build_curl(cfg))
    assert "-u" in parts
    assert parts[parts.index("-u") + 1] == "admin:s3cr3t"


@respx.mock
async def test_curl_reproduces_request_for_all_auth_types():
    """The generated curl must carry the same credential the client sends."""
    cases = {
        "bearer": ("tok123", "Bearer tok123"),
        "apikey": ("X-API-Key: k9", None),
        "basic": ("admin:s3cr3t", "Basic " + base64.b64encode(b"admin:s3cr3t").decode()),
        "none": ("", None),
    }
    for auth_type, (auth_value, _expected) in cases.items():
        route = respx.get("https://api/me").mock(return_value=httpx.Response(200, text="ok"))
        cfg = RequestConfig(method="GET", url="https://api/me", auth_type=auth_type, auth_value=auth_value)
        cmd = build_curl(cfg)
        await send(cfg)
        sent = route.calls.last.request

        if auth_type == "bearer":
            assert sent.headers["authorization"] == "Bearer tok123"
            assert "Authorization: Bearer tok123" in cmd
        elif auth_type == "basic":
            assert sent.headers["authorization"] == cases["basic"][1]
            assert "-u admin:s3cr3t" in cmd  # curl -u produces the same header
        elif auth_type == "apikey":
            assert sent.headers["x-api-key"] == "k9"
            assert "X-API-Key: k9" in cmd
        else:
            assert "authorization" not in sent.headers
        respx.reset()


# --- 1.2 -L must be conditional on follow_redirects -----------------------


def test_no_redirect_omits_dash_L():
    cfg = RequestConfig(method="GET", url="https://x", follow_redirects=False)
    assert "-L" not in _parts(build_curl(cfg))


def test_redirect_default_includes_dash_L():
    cfg = RequestConfig(method="GET", url="https://x")
    assert "-L" in _parts(build_curl(cfg))


# --- 1.3 timeout must show up as --max-time -------------------------------


def test_custom_timeout_emits_max_time():
    cfg = RequestConfig(method="GET", url="https://x", timeout=5.0)
    parts = _parts(build_curl(cfg))
    assert "--max-time" in parts
    assert parts[parts.index("--max-time") + 1] == "5"


def test_default_timeout_omits_max_time():
    cfg = RequestConfig(method="GET", url="https://x")
    assert "--max-time" not in _parts(build_curl(cfg))
