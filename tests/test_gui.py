"""GUI (Textual) tests — repo reuse (1.11) and basic wiring."""

import sqlite3

import pytest

from curlcommander.gui.app import CurlCommanderApp
from curlcommander.gui.history_panel import HistoryPanel


async def test_app_reuses_single_repo_and_closes_it(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        repo = app.repo
        # Panels use the app's connection, not fresh ones.
        app.query_one(HistoryPanel).refresh_history()
        await pilot.pause()
        assert app.repo is repo  # same instance throughout the session
        conn = app.repo._conn

    # After the app unmounts the connection is closed.
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


async def test_footer_and_header_present(tmp_path):
    from textual.widgets import Footer, Header

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test():
        assert app.query_one(Footer)  # shortcuts are now discoverable on screen
        assert app.query_one(Header)


async def test_ctrl_q_quits_even_with_focus_in_input(tmp_path):
    from textual.widgets import Input

    from curlcommander.gui.request_panel import RequestPanel

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        # Focus a text field — the reported bug was that 'q' just typed there.
        app.query_one(RequestPanel).query_one("#url-input", Input).focus()
        await pilot.pause()
        await pilot.press("ctrl+q")
    assert app.return_code == 0  # the app exited cleanly


async def test_quit_button_exits(tmp_path):
    from textual.widgets import Button

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        btn = app.query_one("#quit-btn", Button)
        assert str(btn.label) == "Sair"  # a visible, clickable exit control
        btn.press()
        await pilot.pause()
    assert app.return_code == 0


async def test_app_mounts_all_panels(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test():
        from curlcommander.gui.curl_panel import CurlPanel
        from curlcommander.gui.request_panel import RequestPanel
        from curlcommander.gui.response_panel import ResponsePanel

        assert app.query_one(RequestPanel)
        assert app.query_one(ResponsePanel)
        assert app.query_one(CurlPanel)
        assert app.query_one(HistoryPanel)


async def test_options_panel_reachable_in_config(tmp_path):
    from textual.widgets import Checkbox, Input

    from curlcommander.gui.request_panel import RequestPanel

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        panel = app.query_one(RequestPanel)
        panel.query_one("#url-input", Input).value = "https://x/y"
        panel.query_one("#proxy-input", Input).value = "http://127.0.0.1:8080"
        panel.query_one("#timeout-input", Input).value = "7"
        panel.query_one("#retries-input", Input).value = "2"
        panel.query_one("#verify-checkbox", Checkbox).value = False
        panel.query_one("#redirects-checkbox", Checkbox).value = False
        await pilot.pause()

        cfg = panel.get_config()
        assert cfg.proxy == "http://127.0.0.1:8080"
        assert cfg.timeout == 7.0
        assert cfg.max_retries == 2
        assert cfg.verify_ssl is False
        assert cfg.follow_redirects is False


async def test_response_tabs_present(tmp_path):
    from textual.widgets import TabPane

    from curlcommander.gui.response_panel import ResponsePanel

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test():
        panel = app.query_one(ResponsePanel)
        ids = {p.id for p in panel.query(TabPane)}
        assert {"tab-body", "tab-headers", "tab-raw", "tab-cookies"} <= ids


async def test_gui_send_populates_history(tmp_path, monkeypatch):
    import httpx
    import respx
    from textual.widgets import Input

    from curlcommander.gui.request_panel import RequestPanel

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    with respx.mock:
        respx.get("https://x/y").mock(return_value=httpx.Response(200, text="hi"))
        async with app.run_test() as pilot:
            app.query_one(RequestPanel).query_one("#url-input", Input).value = "https://x/y"
            await pilot.pause()
            app.action_send_request()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.repo.load()  # a history entry was written
            assert app._last_curl.startswith("curl")
