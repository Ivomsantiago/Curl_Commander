"""Native MCP server exposing CurlCommander to any AI assistant (Fase 1).

Thin wrapper over :mod:`curlcommander.core.mcp_tools`. The ``mcp`` SDK is an
optional dependency (the ``[mcp]`` extra) imported lazily, so the rest of the
tool runs without it — the same pattern as the mitmproxy-backed proxy.

Run it with ``curlcmd mcp`` (stdio transport) and point any MCP client
(Claude Desktop, Cursor, Continue, …) at that command. Every request the AI
sends is scope-checked and recorded in the same history store as the CLI/TUI,
so a human can review exactly what the AI did.
"""

from __future__ import annotations

from typing import Any

from curlcommander import __version__
from curlcommander.core import mcp_tools
from curlcommander.core.mcp_tools import MCPToolError, ToolContext


def mcp_available() -> bool:
    try:
        import mcp  # noqa: F401

        return True
    except Exception:
        return False


def require_mcp() -> None:
    if not mcp_available():
        from curlcommander.core import features

        raise mcp_tools.MCPToolError(features.missing_message("mcp"))


def build_server(ctx: ToolContext | None = None) -> Any:
    """Create a FastMCP server with every CurlCommander tool registered."""
    require_mcp()
    from mcp.server.fastmcp import FastMCP

    context = ctx or ToolContext()
    server = FastMCP("CurlCommander", version=__version__)

    @server.tool()  # type: ignore[untyped-decorator]
    async def send_request(request: dict[str, Any]) -> dict[str, Any]:
        """Send one HTTP request and return status, headers, body and its curl.

        ``request``: {url, method, headers, params, cookies, body|json,
        body_type, auth_type, auth_value, follow_redirects, verify_ssl,
        timeout, http2, proxy}. Out-of-scope targets are refused.
        """
        try:
            return await mcp_tools.send_request(request, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    @server.tool()  # type: ignore[untyped-decorator]
    def build_curl(request: dict[str, Any]) -> dict[str, Any]:
        """Return the faithful curl command for a request without sending it."""
        try:
            return mcp_tools.gen_curl(request, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    @server.tool()  # type: ignore[untyped-decorator]
    def import_curl(command: str) -> dict[str, Any]:
        """Parse a curl command string into a structured request config."""
        try:
            return mcp_tools.import_curl(command, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    @server.tool()  # type: ignore[untyped-decorator]
    async def passive_scan(request: dict[str, Any]) -> dict[str, Any]:
        """Send a request and return passive security findings on the response."""
        try:
            return await mcp_tools.passive_scan(request, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    @server.tool()  # type: ignore[untyped-decorator]
    async def active_scan(request: dict[str, Any]) -> dict[str, Any]:
        """Actively scan a request's parameters (XSS/SQLi/SSTI/traversal/redirect)."""
        try:
            return await mcp_tools.active_scan(request, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    @server.tool()  # type: ignore[untyped-decorator]
    async def intruder_attack(attack: dict[str, Any]) -> dict[str, Any]:
        """Run an Intruder attack (sniper|battering-ram|pitchfork|cluster-bomb).

        ``attack``: {base: <request with FUZZ markers>, mode, wordlists:[[...]],
        payloads:[category], concurrency, rate, filters}. Bounded by a
        per-session request cap.
        """
        try:
            return await mcp_tools.intruder_attack(attack, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    @server.tool()  # type: ignore[untyped-decorator]
    def set_scope(entries: list[str]) -> dict[str, Any]:
        """Replace the scope allowlist the AI is confined to (host globs/CIDRs)."""
        return mcp_tools.set_scope(entries, context)

    @server.tool()  # type: ignore[untyped-decorator]
    def get_scope() -> dict[str, Any]:
        """Return the current scope allowlist and engagement label."""
        return mcp_tools.get_scope(context)

    @server.tool()  # type: ignore[untyped-decorator]
    def list_payload_categories() -> dict[str, Any]:
        """List the payload catalog categories available for Intruder."""
        return mcp_tools.list_payload_categories(context)

    @server.tool()  # type: ignore[untyped-decorator]
    def list_plugins() -> dict[str, Any]:
        """List loaded user plugins and the checks they contribute."""
        return mcp_tools.list_plugins(context)

    @server.tool()  # type: ignore[untyped-decorator]
    def history_list(limit: int = 50) -> dict[str, Any]:
        """List recent requests recorded in the shared history store."""
        return mcp_tools.history_list(context, limit=limit)

    @server.tool()  # type: ignore[untyped-decorator]
    def history_get(id: int) -> dict[str, Any]:
        """Fetch one history entry (full config + curl) by id."""
        try:
            return mcp_tools.history_get(id, context)
        except MCPToolError as exc:
            return {"error": str(exc)}

    return server


def run_stdio(ctx: ToolContext | None = None) -> None:
    """Run the MCP server over stdio until the client disconnects."""
    server = build_server(ctx)
    server.run()  # FastMCP defaults to stdio transport
