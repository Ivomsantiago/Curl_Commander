"""Local web GUI backend (graphical interface, Caido-style).

A dependency-free HTTP server (stdlib ``http.server``) that serves the static
single-page UI in ``curlcommander/webui`` and a small JSON API backed by the
same logic layer the MCP server uses (:mod:`curlcommander.core.mcp_tools`).
Run it with ``curlcmd gui`` — it opens a real graphical interface in the
browser, not a terminal UI.

The router (:func:`handle_api`) is a pure function ``(method, path, body, ctx)
-> (status, dict)`` so it is unit-testable without opening a socket. The
threaded server (:func:`serve`) is a thin shell around it.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from curlcommander import __version__
from curlcommander.core import mcp_tools
from curlcommander.core.mcp_tools import MCPToolError, ToolContext


def _webui_dir() -> Path:
    """Locate the bundled ``webui/`` assets, working both from source and from
    a PyInstaller standalone binary.

    ``importlib.resources`` is the frozen-safe path (the same one
    ``payload_catalog`` uses for ``curlcommander/data``); PyInstaller extracts
    ``collect_data_files("curlcommander")`` into ``_MEIPASS/curlcommander/webui``
    and resources resolves there. The ``__file__`` form is only a last resort
    for exotic layouts.
    """
    try:
        from importlib import resources

        base = resources.files("curlcommander").joinpath("webui")
        p = Path(str(base))
        if p.is_dir():
            return p
    except (ModuleNotFoundError, AttributeError, TypeError, OSError):
        pass
    return Path(__file__).resolve().parent.parent / "webui"


WEBUI_DIR = _webui_dir()

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}


def _run(coro: Any) -> Any:
    """Drive one async mcp_tools call to completion in this request thread."""
    return asyncio.run(coro)


def handle_api(method: str, path: str, body: dict[str, Any], ctx: ToolContext) -> tuple[int, dict[str, Any]]:
    """Route one API request to the shared logic layer.

    Returns ``(http_status, json_body)``. Never raises for expected tool errors
    (they become ``{"error": ...}`` with a 400); unexpected ones bubble up to the
    handler which turns them into a 500.
    """
    try:
        if method == "GET" and path == "/api/info":
            return 200, {
                "name": "CurlCommander",
                "version": __version__,
                "engagement": ctx.engagement,
                "scope": ctx.scope_entries,
            }
        if method == "GET" and path == "/api/scope":
            return 200, mcp_tools.get_scope(ctx)
        if method == "POST" and path == "/api/scope":
            return 200, mcp_tools.set_scope(list(body.get("entries", [])), ctx)
        if method == "GET" and path == "/api/history":
            return 200, mcp_tools.history_list(ctx, limit=int(body.get("limit", 100)))
        if method == "GET" and path.startswith("/api/history/"):
            return 200, mcp_tools.history_get(int(path.rsplit("/", 1)[1]), ctx)
        if method == "GET" and path == "/api/payload-categories":
            return 200, mcp_tools.list_payload_categories(ctx)
        if method == "POST" and path == "/api/send":
            return 200, _run(mcp_tools.send_request(body, ctx))
        if method == "POST" and path == "/api/curl":
            return 200, mcp_tools.gen_curl(body, ctx)
        if method == "POST" and path == "/api/import-curl":
            return 200, mcp_tools.import_curl(str(body.get("command", "")), ctx)
        if method == "POST" and path == "/api/passive":
            return 200, _run(mcp_tools.passive_scan(body, ctx))
        if method == "POST" and path == "/api/intruder":
            return 200, _run(mcp_tools.intruder_attack(body, ctx))
        return 404, {"error": f"no such endpoint: {method} {path}"}
    except MCPToolError as exc:
        return 400, {"error": str(exc)}
    except (ValueError, KeyError) as exc:
        return 400, {"error": f"bad request: {exc}"}


def _make_handler(ctx: ToolContext) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        server_version = f"CurlCommander/{__version__}"

        def log_message(self, *args: Any) -> None:  # keep the console quiet
            pass

        # -- helpers --------------------------------------------------------

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_static(self, rel: str) -> None:
            # Serve only files inside WEBUI_DIR (no traversal).
            target = (WEBUI_DIR / rel.lstrip("/")).resolve()
            if not str(target).startswith(str(WEBUI_DIR)) or not target.is_file():
                self._send_json(404, {"error": "not found"})
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _CONTENT_TYPES.get(target.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw.decode("utf-8"))
                return parsed if isinstance(parsed, dict) else {"_": parsed}
            except (ValueError, UnicodeDecodeError):
                return {}

        # -- verbs ----------------------------------------------------------

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/":
                self._send_static("index.html")
            elif path.startswith("/api/"):
                self._dispatch("GET", path, {})
            elif path.startswith("/static/"):
                self._send_static(path[len("/static/") :])
            else:
                # Any other single-segment file (favicon, app.js at root, …).
                self._send_static(path)

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                self._dispatch("POST", path, self._read_body())
            else:
                self._send_json(404, {"error": "not found"})

        def _dispatch(self, method: str, path: str, body: dict[str, Any]) -> None:
            try:
                status, payload = handle_api(method, path, body, ctx)
            except Exception as exc:  # noqa: BLE001 - never leak a traceback to the browser
                self._send_json(500, {"error": f"internal error: {exc}"})
                return
            self._send_json(status, payload)

    return _Handler


def serve(ctx: ToolContext, host: str = "127.0.0.1", port: int = 8777) -> ThreadingHTTPServer:
    """Start the threaded GUI server (non-blocking); returns the server object."""
    handler = _make_handler(ctx)
    httpd = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, name="curlcmd-gui", daemon=True)
    thread.start()
    return httpd
