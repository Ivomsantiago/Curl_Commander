"""H.1/H.2 tests: browser layer + executed-XSS validation against a fixture.

Runs a real Chromium (pre-installed / Playwright-bundled) against a local HTTP
server — never the internet. Skips cleanly when the browser extra is absent.
"""

import html
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from curlcommander.core import browser, scope
from curlcommander.core.browser import BrowserError, BrowserSession, browser_available
from curlcommander.core.validators.base import CONFIRMED

pytestmark = pytest.mark.skipif(not browser_available(), reason="playwright not installed")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        parts = urlsplit(self.path)
        q = parse_qs(parts.query).get("q", [""])[0]
        if parts.path == "/vuln":
            body = f"<html><body>results for {q}</body></html>"  # unescaped -> XSS
        elif parts.path == "/safe":
            body = f"<html><body>results for {html.escape(q)}</body></html>"  # escaped
        else:
            body = "<html><body>home</body></html>"
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_require_browser_message_when_absent(monkeypatch):
    monkeypatch.setattr(browser, "browser_available", lambda: False)
    with pytest.raises(BrowserError):
        browser.require_browser()


async def test_confirmed_reflected_xss(server):
    from curlcommander.core.validators.xss import validate_xss

    async with BrowserSession() as s:
        result = await validate_xss(s, f"{server}/vuln?q=§PAYLOAD§")
    assert result.verdict == CONFIRMED
    assert result.evidence.get("dialogs") or result.evidence.get("sinks")


async def test_safe_endpoint_not_confirmed(server):
    from curlcommander.core.validators.xss import validate_xss

    async with BrowserSession() as s:
        result = await validate_xss(s, f"{server}/safe?q=§PAYLOAD§")
    assert result.verdict != CONFIRMED


async def test_scope_blocks_navigation(server):
    from curlcommander.core.validators.xss import validate_xss

    async with BrowserSession(scope_entries=["only.allowed.com"]) as s:
        with pytest.raises(scope.ScopeError):
            await validate_xss(s, f"{server}/vuln?q=§PAYLOAD§")


async def test_screenshot_written(server, tmp_path):
    from curlcommander.core.validators.xss import validate_xss

    shot = tmp_path / "xss.png"
    async with BrowserSession() as s:
        result = await validate_xss(s, f"{server}/vuln?q=§PAYLOAD§", screenshot_path=str(shot))
    assert result.confirmed
    assert shot.exists() and shot.stat().st_size > 0


def test_cli_validate_xss_writes_evidence(server, tmp_path, monkeypatch):
    """End-to-end: validate xss with --evidence writes screenshot/HAR/trace/DOM."""
    import types

    from curlcommander.cli import runner

    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    ev = tmp_path / "ev"
    args = types.SimpleNamespace(
        subcommand="validate",
        kind="xss",
        url=f"{server}/vuln?q=§PAYLOAD§",
        engagement="ENG-1",
        scope=None,
        origin="x",
        headed=False,
        evidence=str(ev),
        no_verify=True,
        timeout=10.0,
        log_file=None,
        log_level=None,
    )
    rc = runner.run_cli(args)
    assert rc == runner.EXIT_OK
    assert (ev / "xss.png").exists()
    assert (ev / "xss.har").exists()
    assert (ev / "xss-trace.zip").exists()
    assert (ev / "xss-dom.html").exists()
