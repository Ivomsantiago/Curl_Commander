"""H.3 tests: CORS, open-redirect (respx) and clickjacking/CSRF (browser)."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
import respx

from curlcommander.core import scope
from curlcommander.core.browser import BrowserSession, browser_available
from curlcommander.core.headers import HeaderList
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


@respx.mock
async def test_cors_sends_cookie_and_bearer_when_provided():
    """Anonymous CORS is rarely exploitable; --cookie/--auth-bearer let the
    probe run against an authenticated endpoint (the impactful case)."""
    route = respx.get("https://api.t/data").mock(
        return_value=httpx.Response(
            200,
            headers={
                "access-control-allow-origin": "https://evil.example",
                "access-control-allow-credentials": "true",
            },
        )
    )
    creds = HeaderList([("Authorization", "Bearer tok123"), ("Cookie", "session=abc")])
    r = await validate_cors("https://api.t/data", headers=creds)
    assert r.verdict == CONFIRMED
    assert r.evidence["authenticated"] is True
    sent = route.calls.last.request.headers
    assert sent["authorization"] == "Bearer tok123"
    assert sent["cookie"] == "session=abc"
    assert sent["origin"] == "https://evil.example"


@respx.mock
async def test_cors_evidence_marks_unauthenticated_by_default():
    respx.get("https://api.t/data").mock(return_value=httpx.Response(200))
    r = await validate_cors("https://api.t/data")
    assert r.evidence["authenticated"] is False


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


@respx.mock
async def test_open_redirect_forwards_credentials_to_the_target():
    """Many redirect handlers only run (or only redirect somewhere sensitive)
    once logged in, so the initial request must carry --cookie/--auth-bearer.
    httpx correctly strips them again on the cross-origin hop to the canary
    host, matching what a real victim browser would do."""
    route = respx.get("https://target/r").mock(
        return_value=httpx.Response(302, headers={"location": "https://cc-oob.example/"})
    )
    respx.get("https://cc-oob.example/").mock(return_value=httpx.Response(200, text="oob"))
    creds = HeaderList([("Cookie", "session=abc"), ("Authorization", "Bearer tok123")])
    r = await validate_open_redirect("https://target/r?next=§DEST§", headers=creds)
    assert r.verdict == CONFIRMED
    sent = route.calls.last.request.headers
    assert sent["cookie"] == "session=abc"
    assert sent["authorization"] == "Bearer tok123"


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
        if self.path.startswith("/whoami"):
            self._send(f"<html><body>auth={self.headers.get('Authorization', '')}</body></html>")
        elif self.path.startswith("/frameable"):
            self._send("<html><body><h1>bank transfer page</h1></body></html>")
        elif self.path.startswith("/protected"):
            self._send("<html><body>secret</body></html>", {"X-Frame-Options": "DENY"})
        else:
            self._send("<html><body>home</body></html>")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.path.startswith("/transfer-auth"):
            # Only takes effect for the session cookie a validated
            # BrowserSession(cookies=...) is expected to inject.
            if self.headers.get("Cookie") == "session=valid-token":
                self._send("<html><body>transfer completed ok</body></html>")
            else:
                self._send("<html><body>401 unauthorized</body></html>")
        else:
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


# --- credentials reach browser validators (H.6) ---------------------------
#
# clickjacking/csrf build their PoC with page.set_content() instead of
# session.goto(), so BrowserSession's cookie flush (normally lazy, on goto)
# must be triggered explicitly before the framed/submitted target loads —
# otherwise a --cookie session never reaches an authenticated endpoint.


@browser_only
async def test_clickjacking_flushes_pending_cookies_before_framing(server):
    """clickjacking builds its PoC with set_content(), which never triggers
    goto()'s lazy cookie flush — validate_clickjacking must flush explicitly,
    or a --cookie session never even reaches the browser context before the
    target is embedded. (Whether Chromium's SameSite policy then forwards
    that cookie to a cross-origin iframe is the browser's call, not ours —
    this test only proves BrowserSession did its part.)"""
    from curlcommander.core.validators.clickjacking import validate_clickjacking

    cookies = HeaderList([("session", "valid-token")])
    async with BrowserSession(cookies=cookies) as s:
        assert await s.context.cookies() == []  # nothing flushed until used
        await validate_clickjacking(s, f"{server}/frameable")
        applied = await s.context.cookies()
    assert any(c["name"] == "session" and c["value"] == "valid-token" for c in applied)


@browser_only
async def test_csrf_session_cookie_reaches_authenticated_target(server):
    from curlcommander.core.validators.csrf import validate_csrf

    cookies = HeaderList([("session", "valid-token")])
    async with BrowserSession(cookies=cookies) as s:
        r = await validate_csrf(
            s,
            f"{server}/transfer-auth",
            method="POST",
            fields={"amount": "1000"},
            success_contains="transfer completed ok",
        )
    assert r.verdict == CONFIRMED


@browser_only
async def test_csrf_without_cookie_is_not_confirmed(server):
    from curlcommander.core.validators.csrf import validate_csrf

    async with BrowserSession() as s:
        r = await validate_csrf(
            s,
            f"{server}/transfer-auth",
            method="POST",
            fields={"amount": "1000"},
            success_contains="transfer completed ok",
        )
    assert r.verdict != CONFIRMED


@browser_only
async def test_browser_session_extra_headers_reach_the_request(server):
    """--auth-bearer / -H are set on the whole context (extra_http_headers),
    so every request in it carries them, goto()-driven or not."""
    extra = HeaderList([("Authorization", "Bearer tok123")])
    async with BrowserSession(extra_headers=extra) as s:
        page = await s.new_page()
        await s.goto(page, f"{server}/whoami")
        content = await page.content()
        await page.close()
    assert "auth=Bearer tok123" in content


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


@respx.mock
def test_cli_validate_cors_forwards_cookie_bearer_and_header():
    """`curlcmd validate cors --cookie k=v --auth-bearer TOK -H 'X: Y'` must
    reach the actual HTTP request — this is what makes an authenticated CORS
    check possible, the scenario with real impact."""
    from curlcommander.cli import runner

    route = respx.get("https://api.t/data").mock(return_value=httpx.Response(200))
    rc = runner.run_cli(
        _vns(
            cookies=["session=abc", "theme=dark"],
            auth_bearer="tok123",
            headers=["X-Test: yes"],
        )
    )
    assert rc == runner.EXIT_OK
    sent = route.calls.last.request.headers
    assert sent["cookie"] == "session=abc; theme=dark"
    assert sent["authorization"] == "Bearer tok123"
    assert sent["x-test"] == "yes"


def test_cli_validate_browser_absent_degrades(monkeypatch):
    from curlcommander.cli import runner
    from curlcommander.core import browser

    monkeypatch.setattr(browser, "browser_available", lambda: False)
    rc = runner.run_cli(_vns(kind="xss", url="https://t/x?q=§PAYLOAD§"))
    assert rc == runner.EXIT_USAGE  # clear message, not a crash
