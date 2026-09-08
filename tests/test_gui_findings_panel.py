"""Tests for the GUI Achados (Findings) tab (item 9.3)."""

from textual.widgets import Button, DataTable, Select, Static

from curlcommander.config import db_path_for
from curlcommander.gui.app import CurlCommanderApp
from curlcommander.gui.findings_panel import FindingsPanel
from curlcommander.storage.validation_repo import ValidationRepo


def _static_text(static: Static) -> str:
    return str(static._Static__content)  # noqa: SLF001 - no public accessor for Static's content


def _seed(db_path, engagement: str) -> None:
    from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE, ValidationResult

    repo = ValidationRepo(db_path_for(engagement, db_path))
    try:
        repo.save(engagement, ValidationResult("xss", CONFIRMED, "https://t/x", detail="alert fired"), "ts")
        repo.save(engagement, ValidationResult("cors", NOT_VULNERABLE, "https://t/y"), "ts")
    finally:
        repo.close()


async def test_findings_without_engagement_shows_a_clear_message(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-findings"
        await pilot.pause()
        panel = app.query_one(FindingsPanel)
        assert "engajamento" in _static_text(panel.query_one("#fp-status", Static)).lower()
        assert panel.query_one("#fp-table", DataTable).row_count == 0


async def test_findings_lists_persisted_results_and_generates_report(tmp_path):
    db_path = tmp_path / "h.db"
    _seed(db_path, "cliente-x")
    app = CurlCommanderApp(db_path=str(db_path))
    async with app.run_test() as pilot:
        app.engagement = "cliente-x"
        app.query_one("#main-tabs").active = "tab-findings"
        await pilot.pause()
        panel = app.query_one(FindingsPanel)
        panel.query_one("#fp-refresh", Button).press()
        await pilot.pause()

        table = panel.query_one("#fp-table", DataTable)
        assert table.row_count == 2

        import os

        os.chdir(tmp_path)
        panel.query_one("#fp-report", Button).press()
        await pilot.pause()

    out = tmp_path / "curlcommander-report-cliente-x.html"
    assert out.exists()
    assert "cliente-x" in out.read_text(encoding="utf-8")


async def test_findings_severity_filter_hides_non_matching_rows(tmp_path):
    db_path = tmp_path / "h.db"
    _seed(db_path, "cliente-x")
    app = CurlCommanderApp(db_path=str(db_path))
    async with app.run_test() as pilot:
        app.engagement = "cliente-x"
        app.query_one("#main-tabs").active = "tab-findings"
        await pilot.pause()
        panel = app.query_one(FindingsPanel)
        panel.query_one("#fp-refresh", Button).press()
        await pilot.pause()

        table = panel.query_one("#fp-table", DataTable)
        assert table.row_count == 2  # xss (confirmed, high) + cors (not_vulnerable, no severity)

        panel.query_one("#fp-severity", Select).value = "low"
        await pilot.pause()
        assert table.row_count == 0  # xss is "high", not "low"; the NOT_VULNERABLE row has no severity either
