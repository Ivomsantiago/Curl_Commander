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


async def test_active_scan_enforces_scope():
    ctx = ToolContext(scope_entries=["allowed.example"])
    with pytest.raises(MCPToolError):
        await mcp_tools.active_scan({"url": "https://evil.example/?q=1"}, ctx)


@respx.mock
async def test_active_scan_finds_reflected_xss(tmp_path):
    respx.get(url__regex=r"https://x/.*").mock(
        side_effect=lambda r: httpx.Response(200, text=f"echo {r.url.params.get('q', '')}")
    )
    repo = HistoryRepo(tmp_path / "h.db")
    ctx = ToolContext(repo=repo)
    out = await mcp_tools.active_scan({"url": "https://x/s?q=1"}, ctx)
    assert any(f["category"] == "active-xss" for f in out["findings"])
    # Crafted requests are audited under the active-scan origin.
    assert any(e["origin"] == "mcp-active" for e in mcp_tools.history_list(ctx)["entries"])
    repo.close()


def test_set_and_get_scope():
    ctx = ToolContext()
    mcp_tools.set_scope(["a.example", " b.example ", ""], ctx)
    assert ctx.scope_entries == ["a.example", "b.example"]
    assert mcp_tools.get_scope(ctx)["scope"] == ["a.example", "b.example"]


def test_locked_scope_cannot_be_changed_by_caller():
    # An operator-locked scope is a non-widenable boundary for the MCP caller.
    ctx = ToolContext(scope_entries=["only.example"], scope_locked=True)
    with pytest.raises(MCPToolError, match="locked"):
        mcp_tools.set_scope([], ctx)
    with pytest.raises(MCPToolError, match="locked"):
        mcp_tools.set_scope(["evil.example"], ctx)
    assert ctx.scope_entries == ["only.example"]


def test_prepare_disables_redirects_under_scope():
    ctx = ToolContext(scope_entries=["allowed.example"])
    cfg = mcp_tools.config_from_params({"url": "https://allowed.example/"})
    assert cfg.follow_redirects is True
    ctx.prepare(cfg)
    # Auto-redirect off so a 3xx to an out-of-scope host isn't chased blindly.
    assert cfg.follow_redirects is False


def test_prepare_leaves_redirects_when_no_scope():
    ctx = ToolContext()
    cfg = mcp_tools.config_from_params({"url": "https://x/"})
    ctx.prepare(cfg)
    assert cfg.follow_redirects is True


def test_estimate_cluster_bomb_uses_cartesian_product():
    est = mcp_tools.estimate_intruder_requests
    # Three 100-item lists → 1,000,000, not 100.
    assert est("cluster-bomb", [["x"] * 100, ["y"] * 100, ["z"] * 100], None) == 1_000_000
    assert est("battering-ram", [["x"] * 100], None) == 100
    assert est("sniper", [["x"] * 10], ["a", "b", "c"]) == 30


async def test_cluster_bomb_cap_enforced_on_product():
    ctx = ToolContext(max_intruder_requests=5000)
    with pytest.raises(MCPToolError, match="cap"):
        await mcp_tools.intruder_attack(
            {
                "base": {"url": "https://x/?a=FUZZ1&b=FUZZ2", "method": "GET"},
                "mode": "cluster-bomb",
                "wordlists": [["p"] * 100, ["q"] * 100],  # 10,000 > 5,000
            },
            ctx,
        )


@respx.mock
async def test_stored_curl_is_redacted(tmp_path):
    respx.get("https://x/").mock(return_value=httpx.Response(200, text="ok"))
    repo = HistoryRepo(tmp_path / "h.db")
    ctx = ToolContext(repo=repo)
    await mcp_tools.send_request({"url": "https://x/", "headers": {"Authorization": "Bearer SUPERSECRET"}}, ctx)
    listed = mcp_tools.history_list(ctx, limit=1)
    got = mcp_tools.history_get(listed["entries"][0]["id"], ctx)
    assert "SUPERSECRET" not in got["curl"]
    repo.close()


@respx.mock
async def test_passive_scan_is_recorded(tmp_path):
    respx.get("https://x/").mock(return_value=httpx.Response(200, text="ok"))
    repo = HistoryRepo(tmp_path / "h.db")
    ctx = ToolContext(repo=repo)
    await mcp_tools.passive_scan({"url": "https://x/"}, ctx)
    assert repo.count() == 1
    assert mcp_tools.history_list(ctx, limit=1)["entries"][0]["origin"] == "mcp-scan"
    repo.close()


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
