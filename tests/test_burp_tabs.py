"""Fase 1 tests: the Burp-style Proxy / Repeater / Intruder tabs (App.run_test)."""

import httpx
import respx
from textual.widgets import DataTable, Input, Select, TabbedContent, TabPane, TextArea

from curlcommander.core.request_model import RequestConfig, ResponseResult
from curlcommander.gui.app import CurlCommanderApp
from curlcommander.gui.intruder_panel import IntruderPanel, apply_markers, parse_wordlists
from curlcommander.gui.proxy_panel import ProxyPanel
from curlcommander.gui.repeater_panel import RepeaterPanel, RepeaterTab
from curlcommander.gui.response_view import ResponseView, diff_bodies


def _app(tmp_path):
    return CurlCommanderApp(db_path=str(tmp_path / "h.db"))


# --- pure helpers ---------------------------------------------------------


def test_apply_markers_and_parse_wordlists():
    marked, originals, n = apply_markers("GET /x?a=§1§&b=§2§", "cluster-bomb")
    assert n == 2 and originals == ["1", "2"]
    assert "FUZZ1" in marked and "FUZZ2" in marked

    marked_br, _, _ = apply_markers("GET /x?a=§1§&b=§2§", "battering-ram")
    assert marked_br.count("FUZZ") == 2 and "FUZZ1" not in marked_br  # same marker

    # one group reused across positions; N groups map 1:1
    assert parse_wordlists("a\nb", 2, "cluster-bomb") == [["a", "b"], ["a", "b"]]
    assert parse_wordlists("a\nb\n\nc\nd", 2, "cluster-bomb") == [["a", "b"], ["c", "d"]]
    assert parse_wordlists("a\nb\n\nc", 1, "sniper") == [["a", "b"]]


def test_diff_bodies():
    assert diff_bodies("a\nb", "a\nb") == ""
    d = diff_bodies("a\nb", "a\nc")
    assert "atual" in d and "-b" in d and "+c" in d


# --- Repeater -------------------------------------------------------------


@respx.mock
async def test_repeater_multiple_persistent_tabs_and_resend_history(tmp_path):
    respx.get(url__regex=r"https://t/.*").mock(return_value=httpx.Response(200, text="ok"))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        rp = app.query_one(RepeaterPanel)
        ids = [rp.add_request(RequestConfig(method="GET", url=f"https://t/{i}")) for i in range(3)]
        await pilot.pause()
        tabs = rp.query_one("#rp-tabs", TabbedContent)
        assert len(tabs.query(TabPane)) == 3  # three persistent tabs

        first = app.query_one(f"#{ids[0]}", TabPane).query_one(RepeaterTab)
        first._send()
        await app.workers.wait_for_complete()
        first._send()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert first.send_count() == 2  # resend history stacks within the tab

        # other tabs are untouched (state preserved)
        third = app.query_one(f"#{ids[2]}", TabPane).query_one(RepeaterTab)
        assert third.send_count() == 0


# --- Intruder -------------------------------------------------------------


@respx.mock
async def test_intruder_cluster_bomb_populates_grid_with_anomaly(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        # One combination behaves differently → flagged as an anomaly.
        if "a=q" in str(request.url):
            return httpx.Response(500, text="boom-boom-boom")
        return httpx.Response(200, text="ok")

    respx.get(url__regex=r"https://t/x.*").mock(side_effect=handler)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        ip = app.query_one(IntruderPanel)
        ip.load_request(RequestConfig(method="GET", url="https://t/x?a=1&b=2"))
        await pilot.pause()
        ip.query_one("#it-request", TextArea).load_text("GET /x?a=§1§&b=§2§ HTTP/1.1\r\nHost: t\r\n\r\n")
        ip.query_one("#it-payloads", TextArea).load_text("p\nq")
        ip.query_one("#it-mode", Select).value = "cluster-bomb"
        await pilot.pause()
        ip._run()
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = ip.query_one("#it-results", DataTable)
        assert table.row_count == 4  # 2 x 2 combinations
        assert any(r.anomaly for r in ip._results)  # the odd one out is flagged


# --- Proxy ----------------------------------------------------------------


async def test_proxy_capture_and_send_to_repeater(tmp_path):
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        px = app.query_one(ProxyPanel)
        px.add_capture(RequestConfig(method="GET", url="https://t/captured?x=1"), 200, 123, in_scope=True)
        px.add_capture(RequestConfig(method="POST", url="https://evil/z"), 404, 5, in_scope=False)
        await pilot.pause()
        table = px.query_one("#px-table", DataTable)
        assert table.row_count == 2  # out-of-scope stays visible (dimmed), not hidden

        table.move_cursor(row=0)
        px._send_selected(to_intruder=False)
        await pilot.pause()
        assert app.query_one("#main-tabs", TabbedContent).active == "tab-repeater"
        assert len(app.query_one("#rp-tabs", TabbedContent).query(TabPane)) == 1


# --- routing + response viewer -------------------------------------------


async def test_ctrl_r_sends_current_request_to_repeater(tmp_path):
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        from curlcommander.gui.request_panel import RequestPanel

        app.query_one(RequestPanel).query_one("#url-input", Input).value = "https://t/x"
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app.query_one("#main-tabs", TabbedContent).active == "tab-repeater"
        assert len(app.query_one("#rp-tabs", TabbedContent).query(TabPane)) == 1


async def test_response_view_search_count(tmp_path):
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        rp = app.query_one(RepeaterPanel)
        pid = rp.add_request(RequestConfig(method="GET", url="https://t/x"))
        await pilot.pause()
        rv = app.query_one(f"#{pid}", TabPane).query_one(ResponseView)
        rv.show_result(ResponseResult(200, "OK", {}, "foo bar foo baz foo", "text/plain", 1.0, 19, None))
        await pilot.pause()
        rv.query_one("#rv-search", Input).value = "foo"
        await pilot.pause()
        assert rv.match_count() == 3  # "N/total" navigable count


async def test_response_view_analyze_button_reports_candidates(tmp_path):
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        rp = app.query_one(RepeaterPanel)
        pid = rp.add_request(RequestConfig(method="GET", url="https://t/x"))
        await pilot.pause()
        rv = app.query_one(f"#{pid}", TabPane).query_one(ResponseView)
        # A wide-open response: no security headers, a flagless cookie.
        rv.show_result(
            ResponseResult(200, "OK", {"set-cookie": "sid=1"}, "hi", "text/html", 1.0, 2, None),
            url="https://t/x",
        )
        await pilot.pause()
        assert rv.analyze() > 0  # passive analysis surfaced candidates


async def test_request_panel_has_http2_compressed_cookies(tmp_path):
    from textual.widgets import Checkbox

    from curlcommander.gui.request_panel import RequestPanel

    app = _app(tmp_path)
    async with app.run_test() as pilot:
        panel = app.query_one(RequestPanel)
        panel.query_one("#url-input", Input).value = "https://x/y"
        panel.query_one("#http2-checkbox", Checkbox).value = True
        panel.query_one("#compressed-checkbox", Checkbox).value = True
        panel.query_one("#cookies-input", Input).value = "a=1; b=2"
        await pilot.pause()
        cfg = panel.get_config()
        assert cfg.http2 is True and cfg.compressed is True
        assert cfg.cookies.get("a") == "1" and cfg.cookies.get("b") == "2"
