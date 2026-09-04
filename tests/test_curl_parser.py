"""Tests for 2.1 curl import and 2.2 raw HTTP import."""

import pytest

from curlcommander.core.curl_builder import build_curl
from curlcommander.core.curl_parser import CurlParseError, parse_curl
from curlcommander.core.headers import HeaderList
from curlcommander.core.raw_http import RawRequestError, parse_raw_request
from curlcommander.core.request_model import RequestConfig


def test_import_devtools_style():
    cmd = (
        "curl 'https://api.x/y?a=1&a=2' -X POST "
        "-H 'Content-Type: application/json' -H 'Cookie: s=1' "
        "--data-raw '{\"k\":\"v\"}'"
    )
    cfg = parse_curl(cmd)
    assert cfg.method == "POST"
    assert cfg.url == "https://api.x/y"
    assert cfg.params.get_all("a") == ["1", "2"]  # HPP preserved
    assert cfg.headers.get("Content-Type") == "application/json"
    assert cfg.headers.get("Cookie") == "s=1"
    assert cfg.body == '{"k":"v"}'


def test_import_flags():
    cmd = "curl -k -L --compressed --http2 --max-time 7 -x http://127.0.0.1:8080 -u a:b https://x/y"
    cfg = parse_curl(cmd)
    assert cfg.verify_ssl is False
    assert cfg.follow_redirects is True
    assert cfg.compressed and cfg.http2
    assert cfg.timeout == 7.0
    assert cfg.proxy == "http://127.0.0.1:8080"
    assert cfg.auth_type == "basic" and cfg.auth_value == "a:b"


def test_import_line_continuations_and_useragent_referer():
    cmd = "curl https://x/y \\\n -A 'MyAgent' \\\n -e 'https://ref' "
    cfg = parse_curl(cmd)
    assert cfg.headers.get("User-Agent") == "MyAgent"
    assert cfg.headers.get("Referer") == "https://ref"


def test_import_windows_caret_continuation():
    cmd = "curl https://x/y ^\n -H \"Accept: application/json\""
    cfg = parse_curl(cmd)
    assert cfg.headers.get("Accept") == "application/json"


def test_import_rejects_non_curl():
    with pytest.raises(CurlParseError):
        parse_curl("wget https://x/y")


def _cfgs():
    return [
        RequestConfig(method="GET", url="https://x/y"),
        RequestConfig(
            method="POST", url="https://api.x/z",
            headers=[("X-A", "1"), ("X-A", "2"), ("Accept", "application/json")],
            params=[("id", "1"), ("id", "2")],
            body='{"n":1}', body_type="json",
        ),
        RequestConfig(method="PUT", url="https://x/y", verify_ssl=False, follow_redirects=True,
                      compressed=True, timeout=12.0, proxy="http://127.0.0.1:8080"),
        RequestConfig(method="POST", url="https://x/y", auth_type="basic", auth_value="user:pass"),
    ]


@pytest.mark.parametrize("cfg", _cfgs())
def test_round_trip_parse_of_build(cfg):
    """parse(build(cfg)) must recover the request-shaping fields."""
    reparsed = parse_curl(build_curl(cfg))
    assert reparsed.method == cfg.method
    assert reparsed.url == cfg.url
    assert reparsed.headers.get_all("X-A") == cfg.headers.get_all("X-A")
    assert reparsed.params.items() == cfg.params.items()
    assert reparsed.verify_ssl == cfg.verify_ssl
    assert reparsed.follow_redirects == cfg.follow_redirects
    assert reparsed.compressed == cfg.compressed
    if cfg.auth_type == "basic":
        assert reparsed.auth_value == cfg.auth_value


# --- 2.2 raw HTTP ---------------------------------------------------------

def test_raw_request_with_host_header():
    raw = "POST /login HTTP/1.1\r\nHost: target.com\r\nContent-Type: application/json\r\n\r\n{\"u\":\"a\"}"
    cfg = parse_raw_request(raw)
    assert cfg.method == "POST"
    assert cfg.url == "https://target.com/login"
    assert cfg.body == '{"u":"a"}'


def test_raw_request_with_host_override():
    raw = "GET /admin HTTP/1.1\r\nHost: internal\r\n\r\n"
    cfg = parse_raw_request(raw, host="http://10.0.0.5:8080")
    assert cfg.url == "http://10.0.0.5:8080/admin"


def test_raw_request_no_host_errors():
    with pytest.raises(RawRequestError):
        parse_raw_request("GET /x HTTP/1.1\r\n\r\n")
