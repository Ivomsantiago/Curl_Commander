"""H.3 tests: CORS, open-redirect (respx) and clickjacking/CSRF (browser)."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
import respx

from curlcommander.core import scope
from curlcommander.core.browser import BrowserSession, browser_available
from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE
from curlcommander.core.validators.cors import validate_cors
from curlcommander.core.validators.redirect import validate_open_redirect

# --- CORS (respx) ---------------------------------------------------------


@respx.mock
async def test_cors_confirmed_reflected_with_credentials():
    respx.get("https://api.t/data").mock(
        return_value=httpx.Response(
            200,
            headers={
                "access-control-allow-origin": "https://evil.example",
                "access-control-allow-credentials": "true",
            },
        )
    )
    r = await validate_cors("https://api.t/data")
    assert r.verdict == CONFIRMED


@respx.mock
async def test_cors_wildcard_is_reflected_not_confirmed():
    respx.get("https://api.t/data").mock(return_value=httpx.Response(200, headers={"access-control-allow-origin": "*"}))
    r = await validate_cors("https://api.t/data")
    assert r.verdict == "REFLECTED"


@respx.mock
async def test_cors_not_vulnerable():
    respx.get("https://api.t/data").mock(return_value=httpx.Response(200))
    r = await validate_cors("https://api.t/data")
    assert r.verdict == NOT_VULNERABLE


# --- open redirect (respx) ------------------------------------------------


@respx.mock
async def test_open_redirect_confirmed():
    respx.get("https://target/r").mock(
        return_value=httpx.Response(302, headers={"location": "https://cc-oob.example/"})
    )
    respx.get("https://cc-oob.example/").mock(return_value=httpx.Response(200, text="oob"))
    r = await validate_open_redirect("https://target/r?next=§DEST§")
    assert r.verdict == CONFIRMED


@respx.mock
async def test_open_redirect_not_vulnerable():
    respx.get("https://target/r").mock(return_value=httpx.Response(200, text="home"))
    r = await validate_open_redirect("https://target/r?next=§DEST§")
    assert r.verdict == NOT_VULNERABLE


# --- browser validators (real Chromium against a fixture) -----------------

browser_only = pytest.mark.skipif(not browser_available(), reason="playwright not installed")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: str, headers: dict | None = None):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/frameable"):
            self._send("<html><body><h1>bank transfer page</h1></body></html>")
        elif self.path.startswith("/protected"):
            self._send("<html><body>secret</body></html>", {"X-Frame-Options": "DENY"})
        else:
            self._send("<html><body>home</body></html>")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self._send("<html><body>transfer completed ok</body></html>")


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@browser_only
async def test_clickjacking_confirmed_on_frameable(server, tmp_path):
    from curlcommander.core.validators.clickjacking import validate_clickjacking

    shot = tmp_path / "cj.png"
    async with BrowserSession() as s:
        r = await validate_clickjacking(s, f"{server}/frameable", screenshot_path=str(shot))
    assert r.verdict == CONFIRMED
    assert shot.exists()


@browser_only
async def test_clickjacking_blocked_on_protected(server):
    from curlcommander.core.validators.clickjacking import validate_clickjacking

    async with BrowserSession() as s:
        r = await validate_clickjacking(s, f"{server}/protected")
    assert r.verdict == NOT_VULNERABLE


@browser_only
async def test_csrf_effect_confirmed(server):
    from curlcommander.core.validators.csrf import validate_csrf

    async with BrowserSession() as s:
        r = await validate_csrf(
            s,
            f"{server}/transfer",
            method="POST",
            fields={"amount": "1000"},
            success_contains="transfer completed",
        )
    assert r.verdict == CONFIRMED


@browser_only
async def test_clickjacking_scope_enforced(server):
    from curlcommander.core.validators.clickjacking import validate_clickjacking

    async with BrowserSession(scope_entries=["only.allowed.com"]) as s:
        with pytest.raises(scope.ScopeError):
            await validate_clickjacking(s, f"{server}/frameable")


# --- validate CLI ---------------------------------------------------------


def _vns(**kw):
    import types

    base = dict(
        subcommand="validate",
        kind="cors",
        url="https://api.t/data",
        engagement="ENG-1",
        scope=None,
        origin="https://evil.example",
        headed=False,
        evidence=None,
        no_verify=False,
        timeout=5.0,
        log_file=None,
        log_level=None,
    )
    base.update(kw)
    return types.SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    from curlcommander.cli import runner

    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")


@respx.mock
def test_cli_validate_cors_confirmed():
    from curlcommander.cli import runner

    respx.get("https://api.t/data").mock(
        return_value=httpx.Response(
            200,
            headers={
                "access-control-allow-origin": "https://evil.example",
                "access-control-allow-credentials": "true",
            },
        )
    )
    assert runner.run_cli(_vns()) == runner.EXIT_OK


def test_cli_validate_requires_engagement():
    from curlcommander.cli import runner

    assert runner.run_cli(_vns(engagement=None)) == runner.EXIT_USAGE


def test_cli_validate_browser_absent_degrades(monkeypatch):
    from curlcommander.cli import runner
    from curlcommander.core import browser

    monkeypatch.setattr(browser, "browser_available", lambda: False)
    rc = runner.run_cli(_vns(kind="xss", url="https://t/x?q=§PAYLOAD§"))
    assert rc == runner.EXIT_USAGE  # clear message, not a crash
