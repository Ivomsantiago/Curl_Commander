"""Tests for the MCP logic layer (curlcommander.core.mcp_tools).

These exercise the pure logic without needing the optional ``mcp`` SDK.
"""

import httpx
import pytest
import respx

from curlcommander.core import mcp_tools
from curlcommander.core.mcp_tools import MCPToolError, ToolContext
from curlcommander.storage.history_repo import HistoryRepo


def test_config_from_params_requires_url():
    with pytest.raises(MCPToolError):
        mcp_tools.config_from_params({"method": "GET"})


def test_config_from_params_json_alias_sets_body_and_type():
    cfg = mcp_tools.config_from_params({"url": "https://x/", "method": "POST", "json": {"a": 1}})
    assert cfg.body == '{"a": 1}'
    assert cfg.body_type == "json"


def test_config_from_params_headers_mapping():
    cfg = mcp_tools.config_from_params({"url": "https://x/", "headers": {"X-Test": "1"}})
    assert cfg.headers["X-Test"] == "1"


@respx.mock
async def test_send_request_returns_summary_and_curl(tmp_path):
    respx.get("https://api.example.com/").mock(
        return_value=httpx.Response(200, text="ok", headers={"content-type": "text/plain"})
    )
    repo = HistoryRepo(tmp_path / "h.db")
    ctx = ToolContext(repo=repo, engagement="eng1")
    out = await mcp_tools.send_request({"url": "https://api.example.com/"}, ctx)
    assert out["response"]["status_code"] == 200
    assert out["response"]["body"] == "ok"
    assert out["curl"].startswith("curl")
    # Recorded in history under the engagement.
    assert out["history_id"] is not None
    assert repo.count() == 1
    repo.close()


async def test_send_request_enforces_scope():
    ctx = ToolContext(scope_entries=["allowed.example"])
    with pytest.raises(MCPToolError):
        await mcp_tools.send_request({"url": "https://evil.example/"}, ctx)


@respx.mock
async def test_send_request_allows_in_scope():
    respx.get("https://allowed.example/").mock(return_value=httpx.Response(204))
    ctx = ToolContext(scope_entries=["allowed.example"])
    out = await mcp_tools.send_request({"url": "https://allowed.example/"}, ctx)
    assert out["response"]["status_code"] == 204


def test_import_curl_roundtrips():
    out = mcp_tools.import_curl("curl -X POST https://x/api -H 'X-A: b'", ToolContext())
    cfg = out["config"]
    assert cfg["method"] == "POST"
    assert cfg["url"] == "https://x/api"


def test_import_curl_rejects_empty():
    with pytest.raises(MCPToolError):
        mcp_tools.import_curl("   ", ToolContext())


@respx.mock
async def test_passive_scan_reports_findings():
    respx.get("https://x/").mock(return_value=httpx.Response(200, text="ok", headers={"content-type": "text/html"}))
    out = await mcp_tools.passive_scan({"url": "https://x/"}, ToolContext())
    # Missing security headers on an HTML response yield at least one finding.
    assert out["status_code"] == 200
    assert isinstance(out["findings"], list)
    assert any("category" in f for f in out["findings"])


async def test_intruder_attack_respects_cap():
    ctx = ToolContext(max_intruder_requests=2)
    with pytest.raises(MCPToolError):
        await mcp_tools.intruder_attack(
            {
                "base": {"url": "https://x/?q=FUZZ", "method": "GET"},
                "mode": "sniper",
                "wordlists": [["a", "b", "c"]],
            },
            ctx,
        )


@respx.mock
async def test_intruder_attack_runs(tmp_path):
    respx.get(url__regex=r"https://x/.*").mock(return_value=httpx.Response(200, text="x"))
    ctx = ToolContext()
    out = await mcp_tools.intruder_attack(
        {
            "base": {"url": "https://x/?q=FUZZ", "method": "GET"},
            "mode": "battering-ram",
            "wordlists": [["a", "b"]],
        },
        ctx,
    )
    assert out["mode"] == "battering-ram"
    assert out["count"] == 2


async def test_intruder_sniper_requires_originals():
    ctx = ToolContext()
    with pytest.raises(MCPToolError, match="sniper"):
        await mcp_tools.intruder_attack(
            {
                "base": {"url": "https://x/?q=FUZZ", "method": "GET"},
                "mode": "sniper",
                "wordlists": [["a", "b"]],
            },
            ctx,
        )


def test_set_and_get_scope():
    ctx = ToolContext()
    mcp_tools.set_scope(["a.example", " b.example ", ""], ctx)
    assert ctx.scope_entries == ["a.example", "b.example"]
    assert mcp_tools.get_scope(ctx)["scope"] == ["a.example", "b.example"]


@respx.mock
async def test_history_list_and_get(tmp_path):
    respx.get("https://x/").mock(return_value=httpx.Response(200, text="ok"))
    repo = HistoryRepo(tmp_path / "h.db")
    ctx = ToolContext(repo=repo)
    await mcp_tools.send_request({"url": "https://x/"}, ctx)
    listed = mcp_tools.history_list(ctx, limit=10)
    assert len(listed["entries"]) == 1
    eid = listed["entries"][0]["id"]
    got = mcp_tools.history_get(eid, ctx)
    assert got["config"]["url"] == "https://x/"
    repo.close()


def test_history_get_unknown_raises(tmp_path):
    repo = HistoryRepo(tmp_path / "h.db")
    with pytest.raises(MCPToolError):
        mcp_tools.history_get(999, ToolContext(repo=repo))
    repo.close()
