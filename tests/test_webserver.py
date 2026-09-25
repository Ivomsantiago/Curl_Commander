"""Tests for the graphical web GUI backend (curlcommander.core.webserver).

The router handle_api() is pure, so it is tested without opening a socket; one
end-to-end smoke test boots the threaded server and hits it over HTTP.
"""

import json
import urllib.error
import urllib.request

import httpx
import respx

from curlcommander.core import webserver
from curlcommander.core.mcp_tools import ToolContext
from curlcommander.storage.history_repo import HistoryRepo


def test_info_endpoint():
    ctx = ToolContext(engagement="ENG")
    status, body = webserver.handle_api("GET", "/api/info", {}, ctx)
    assert status == 200
    assert body["name"] == "CurlCommander"
    assert body["engagement"] == "ENG"


def test_scope_get_and_set():
    ctx = ToolContext()
    status, body = webserver.handle_api("POST", "/api/scope", {"entries": ["a.example", "b.example"]}, ctx)
    assert status == 200 and body["scope"] == ["a.example", "b.example"]
    status, body = webserver.handle_api("GET", "/api/scope", {}, ctx)
    assert body["scope"] == ["a.example", "b.example"]


def test_curl_endpoint():
    ctx = ToolContext()
    status, body = webserver.handle_api("POST", "/api/curl", {"url": "https://x/", "method": "GET"}, ctx)
    assert status == 200 and body["curl"].startswith("curl")


def test_unknown_endpoint_404():
    status, body = webserver.handle_api("GET", "/api/nope", {}, ToolContext())
    assert status == 404 and "error" in body


def test_send_out_of_scope_is_400():
    ctx = ToolContext(scope_entries=["allowed.example"])
    status, body = webserver.handle_api("POST", "/api/send", {"url": "https://evil.example/"}, ctx)
    assert status == 400 and "error" in body


@respx.mock
def test_send_and_history_roundtrip(tmp_path):
    respx.get("https://x/").mock(return_value=httpx.Response(200, text="ok"))
    ctx = ToolContext(repo=HistoryRepo(tmp_path / "h.db"))
    status, body = webserver.handle_api("POST", "/api/send", {"url": "https://x/"}, ctx)
    assert status == 200 and body["response"]["status_code"] == 200
    status, body = webserver.handle_api("GET", "/api/history", {}, ctx)
    assert len(body["entries"]) == 1
    ctx.repo.close()


def test_static_serving_is_allowlisted(tmp_path):
    # Known assets serve; anything else (including traversal) is 404 — the
    # server never builds a filesystem path from an attacker-controlled string.
    ctx = ToolContext()
    httpd = webserver.serve(ctx, host="127.0.0.1", port=0)
    try:
        port = httpd.server_address[1]

        def get(p):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{p}")
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        assert get("/static/app.js") == 200
        assert get("/static/style.css") == 200
        # Traversal / unknown files are refused.
        assert get("/static/..%2f..%2f..%2fetc%2fpasswd") == 404
        assert get("/static/../../../../etc/passwd") == 404
        assert get("/static/webserver.py") == 404
        assert get("/etc/passwd") == 404
    finally:
        httpd.shutdown()


@respx.mock
def test_server_smoke(tmp_path):
    respx.get("https://x/").mock(return_value=httpx.Response(200, text="ok"))
    ctx = ToolContext(repo=HistoryRepo(tmp_path / "h.db"))
    httpd = webserver.serve(ctx, host="127.0.0.1", port=0)
    try:
        port = httpd.server_address[1]
        # index.html is served at /
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            assert r.status == 200
            assert b"CurlCommander" in r.read()
        # info API
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info") as r:
            info = json.loads(r.read())
            assert info["name"] == "CurlCommander"
    finally:
        httpd.shutdown()
        ctx.repo.close()
