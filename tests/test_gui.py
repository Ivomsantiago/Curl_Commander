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
