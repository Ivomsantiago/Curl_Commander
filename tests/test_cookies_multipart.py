"""Tests for 2.3 cookies/sessions and 2.4 multipart upload."""

import httpx
import respx

from curlcommander.core.cookies import load_jar, save_jar
from curlcommander.core.curl_builder import build_curl
from curlcommander.core.headers import HeaderList
from curlcommander.core.http_client import send
from curlcommander.core.multipart import build_multipart, parse_form_field
from curlcommander.core.redaction import REDACTED, redact_config
from curlcommander.core.request_model import RequestConfig


# --- 2.3 cookies ----------------------------------------------------------

@respx.mock
async def test_explicit_cookies_are_sent():
    route = respx.get("https://x/y").mock(return_value=httpx.Response(200, text="ok"))
    cfg = RequestConfig(method="GET", url="https://x/y", cookies=[("sid", "abc"), ("theme", "dark")])
    await send(cfg)
    cookie_header = route.calls.last.request.headers.get("cookie", "")
    assert "sid=abc" in cookie_header and "theme=dark" in cookie_header


@respx.mock
async def test_cookie_jar_persists_set_cookie(tmp_path):
    jar = tmp_path / "jar.json"
    respx.get("https://x/login").mock(
        return_value=httpx.Response(200, headers={"set-cookie": "session=xyz; Path=/"}, text="ok")
    )
    cfg = RequestConfig(method="GET", url="https://x/login", cookie_jar=str(jar))
    await send(cfg)
    assert jar.exists()
    cookies = load_jar(jar)
    assert cookies.get("session") == "xyz"


def test_curl_builder_emits_cookies():
    cfg = RequestConfig(method="GET", url="https://x", cookies=[("a", "1"), ("b", "2")])
    assert "-b 'a=1; b=2'" in build_curl(cfg)


def test_cookies_are_redacted():
    cfg = RequestConfig(method="GET", url="https://x", cookies=[("session", "supersecret")])
    red = redact_config(cfg, {})
    assert red.cookies.get("session") == REDACTED


# --- 2.4 multipart --------------------------------------------------------

def test_parse_form_data_field():
    assert parse_form_field("user", "ada") == ("data", "ada")


def test_parse_form_file(tmp_path):
    f = tmp_path / "up.txt"
    f.write_bytes(b"hello")
    kind, value = parse_form_field("file", f"@{f};type=text/plain;filename=custom.txt")
    assert kind == "file"
    filename, data, ctype = value
    assert filename == "custom.txt" and data == b"hello" and ctype == "text/plain"


@respx.mock
async def test_multipart_upload_sent(tmp_path):
    f = tmp_path / "up.bin"
    f.write_bytes(b"\x00\x01\x02")
    route = respx.post("https://x/upload").mock(return_value=httpx.Response(200, text="ok"))
    cfg = RequestConfig(
        method="POST", url="https://x/upload",
        form=[("field", "value"), ("file", f"@{f};filename=payload.bin")],
    )
    await send(cfg)
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("multipart/form-data")
    assert b"payload.bin" in sent.content
    assert b"\x00\x01\x02" in sent.content


def test_curl_builder_emits_form():
    import shlex
    cfg = RequestConfig(method="POST", url="https://x", form=[("f", "@/tmp/x.png")])
    parts = shlex.split(build_curl(cfg))
    assert "-F" in parts and parts[parts.index("-F") + 1] == "f=@/tmp/x.png"
