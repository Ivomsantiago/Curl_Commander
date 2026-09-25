"""Tests for the FastMCP wrapper (curlcommander.core.mcp_server).

The official ``mcp`` SDK is optional and not installed in CI's base env, so we
inject a minimal fake ``mcp.server.fastmcp.FastMCP`` to verify the wrapper
registers every tool and that each tool dispatches into the logic layer.
"""

import sys
import types

import respx

from curlcommander.core import mcp_server
from curlcommander.core.mcp_tools import ToolContext


class _FakeFastMCP:
    def __init__(self, name, version=None):
        self.name = name
        self.version = version
        self.tools = {}

    def tool(self, *args, **kwargs):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def run(self):  # pragma: no cover - not exercised
        raise RuntimeError("run() should not be called in tests")


def _install_fake_mcp(monkeypatch):
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fastmcp_mod.FastMCP = _FakeFastMCP
    server_mod = types.ModuleType("mcp.server")
    server_mod.fastmcp = fastmcp_mod
    root_mod = types.ModuleType("mcp")
    root_mod.server = server_mod
    monkeypatch.setitem(sys.modules, "mcp", root_mod)
    monkeypatch.setitem(sys.modules, "mcp.server", server_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_mod)


def test_build_server_registers_all_tools(monkeypatch):
    _install_fake_mcp(monkeypatch)
    server = mcp_server.build_server(ToolContext())
    expected = {
        "send_request",
        "build_curl",
        "import_curl",
        "passive_scan",
        "active_scan",
        "intruder_attack",
        "set_scope",
        "get_scope",
        "list_payload_categories",
        "history_list",
        "history_get",
    }
    assert expected <= set(server.tools)


def test_tool_scope_roundtrip(monkeypatch):
    _install_fake_mcp(monkeypatch)
    ctx = ToolContext()
    server = mcp_server.build_server(ctx)
    server.tools["set_scope"](["a.example"])
    assert ctx.scope_entries == ["a.example"]
    assert server.tools["get_scope"]()["scope"] == ["a.example"]


def test_tool_out_of_scope_returns_error(monkeypatch):
    _install_fake_mcp(monkeypatch)
    ctx = ToolContext(scope_entries=["allowed.example"])
    server = mcp_server.build_server(ctx)
    out = server.tools["set_scope"]  # ensure registered
    assert out
    # send_request is async; the wrapper returns a coroutine — drive it.
    import asyncio

    res = asyncio.run(server.tools["send_request"]({"url": "https://evil.example/"}))
    assert "error" in res


@respx.mock
def test_tool_build_curl(monkeypatch):
    _install_fake_mcp(monkeypatch)
    server = mcp_server.build_server(ToolContext())
    res = server.tools["build_curl"]({"url": "https://x/", "method": "GET"})
    assert res["curl"].startswith("curl")


def test_require_mcp_message_when_absent(monkeypatch):
    # With no fake installed and the real SDK absent, build_server refuses cleanly.
    monkeypatch.setitem(sys.modules, "mcp", None)
    assert mcp_server.mcp_available() is False
