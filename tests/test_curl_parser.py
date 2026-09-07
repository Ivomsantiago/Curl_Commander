"""Tests for 2.1 curl import and 2.2 raw HTTP import."""

import pytest

from curlcommander.core.curl_builder import build_curl
from curlcommander.core.curl_parser import CurlParseError, parse_curl
from curlcommander.core.raw_http import RawRequestError, parse_raw_request
from curlcommander.core.request_model import RequestConfig


def test_import_devtools_style():
    cmd = (
        "curl 'https://api.x/y?a=1&a=2' -X POST "
        "-H 'Content-Type: application/json' -H 'Cookie: s=1' "
        '--data-raw \'{"k":"v"}\''
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
    cmd = 'curl https://x/y ^\n -H "Accept: application/json"'
    cfg = parse_curl(cmd)
    assert cfg.headers.get("Accept") == "application/json"


def test_import_rejects_non_curl():
    with pytest.raises(CurlParseError):
        parse_curl("wget https://x/y")


# --- Windows "Copy as cURL (cmd)" export (cmd.exe caret escaping) ---------


def test_import_cmd_export_url_and_cookie_percent_encoding():
    """Chrome/Firefox devtools on Windows escape every char of the value with
    ``^``; a literal ``%3D%3D`` in a cookie comes out as ``^%^3D^%^3D``."""
    cmd = (
        'curl --url ^"https://api.example.com/data?token=1%3D2^" ^\n'
        '  -H ^"Cookie: session=abc^%^3D^%^3D; theme=dark^" ^\n'
        "  --compressed"
    )
    cfg = parse_curl(cmd)
    assert cfg.url == "https://api.example.com/data"
    assert cfg.params.items() == [("token", "1=2")]
    assert cfg.headers.get("Cookie") == "session=abc%3D%3D; theme=dark"
    assert cfg.compressed is True


def test_import_cmd_export_nested_quotes_in_sec_ch_ua():
    """A nested literal ``"`` inside a header value (e.g. Sec-CH-UA) is
    escaped as ``^^"`` — doubled caret — distinct from the single ``^"`` that
    wraps the whole value; both must round-trip to the real header text."""
    cmd = (
        'curl --url ^"https://api.example.com/^" ^\n'
        '  -H ^"sec-ch-ua: ^^"Chromium^^";v=^^"120^^", ^^"Not)A;Brand^^";v=^^"24^^"^" ^\n'
        '  -H ^"accept: application/json^"'
    )
    cfg = parse_curl(cmd)
    assert cfg.url == "https://api.example.com/"
    assert cfg.headers.get("sec-ch-ua") == '"Chromium";v="120", "Not)A;Brand";v="24"'
    assert cfg.headers.get("accept") == "application/json"


def test_import_cmd_export_positional_url_and_multiple_headers():
    cmd = (
        'curl ^"https://target/api/login^" ^\n'
        '  -H ^"Content-Type: application/json^" ^\n'
        '  -H ^"Cookie: a=1^&b=2^" ^\n'
        '  --data-raw ^"{^^\\"u^^\\":^^\\"x^^\\"}^"'
    )
    cfg = parse_curl(cmd)
    assert cfg.url == "https://target/api/login"
    assert cfg.headers.get("Content-Type") == "application/json"
    assert cfg.headers.get("Cookie") == "a=1&b=2"
    assert cfg.body == '{"u":"x"}'


def test_import_bash_command_with_literal_caret_is_not_treated_as_cmd_export():
    """A real bash command whose quoted value happens to contain a bare ``^``
    must not be mangled — the cmd-export heuristic requires ``^"`` right
    after ``curl``/``--url``/``-H``/``-b``, never a lone caret elsewhere."""
    cmd = "curl 'https://x/y' -H 'X-Signature: abc^def==' -d 'a=1'"
    cfg = parse_curl(cmd)
    assert cfg.headers.get("X-Signature") == "abc^def=="
    assert cfg.body == "a=1"


def test_import_windows_caret_continuation_still_uses_old_path():
    """Regular (non cmd-export) caret line continuation, no ``^"`` markers."""
    cmd = 'curl https://x/y ^\n -H "Accept: application/json"'
    cfg = parse_curl(cmd)
    assert cfg.headers.get("Accept") == "application/json"


def _cfgs():
    return [
        RequestConfig(method="GET", url="https://x/y"),
        RequestConfig(
            method="POST",
            url="https://api.x/z",
            headers=[("X-A", "1"), ("X-A", "2"), ("Accept", "application/json")],
            params=[("id", "1"), ("id", "2")],
            body='{"n":1}',
            body_type="json",
        ),
        RequestConfig(
            method="PUT",
            url="https://x/y",
            verify_ssl=False,
            follow_redirects=True,
            compressed=True,
            timeout=12.0,
            proxy="http://127.0.0.1:8080",
        ),
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
    raw = 'POST /login HTTP/1.1\r\nHost: target.com\r\nContent-Type: application/json\r\n\r\n{"u":"a"}'
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
