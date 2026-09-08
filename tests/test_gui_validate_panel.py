"""Tests for the GUI Validate tab (item 9.1) — the open-redirect/cors paths
need no browser/OOB extra, so they're the ones exercised end-to-end here."""

import httpx
import respx
from textual.widgets import Button, Input, Select, Static

from curlcommander.config import db_path_for
from curlcommander.gui.app import CurlCommanderApp
from curlcommander.gui.validate_panel import ValidatePanel
from curlcommander.storage.validation_repo import ValidationRepo


def _static_text(static: Static) -> str:
    return str(static._Static__content)  # noqa: SLF001 - no public accessor for Static's content


async def test_validate_refuses_without_engagement(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-validate"
        await pilot.pause()
        panel = app.query_one(ValidatePanel)
        panel.query_one("#va-kind", Select).value = "open-redirect"
        panel.query_one("#va-url", Input).value = "https://api.target.com/redirect?next=§DEST§"
        panel.query_one("#va-run", Button).press()
        await pilot.pause()
        assert "engajamento" in _static_text(panel.query_one("#va-result", Static)).lower()


@respx.mock
async def test_validate_open_redirect_confirms_and_persists(tmp_path):
    respx.get(url__regex=r"https://api\.target\.com/redirect.*").mock(
        return_value=httpx.Response(302, headers={"Location": "https://cc-oob.example/"})
    )
    respx.get(url__regex=r"https://cc-oob\.example/?").mock(return_value=httpx.Response(200, text="ok"))
    db_path = tmp_path / "h.db"
    app = CurlCommanderApp(db_path=str(db_path))
    async with app.run_test() as pilot:
        app.engagement = "cliente-x"
        app.query_one("#main-tabs").active = "tab-validate"
        await pilot.pause()
        panel = app.query_one(ValidatePanel)
        panel.query_one("#va-kind", Select).value = "open-redirect"
        panel.query_one("#va-url", Input).value = "https://api.target.com/redirect?next=§DEST§"
        panel.query_one("#va-run", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

    repo = ValidationRepo(db_path_for("cliente-x", db_path))
    try:
        stored = repo.load("cliente-x")
    finally:
        repo.close()
    assert len(stored) == 1
    assert stored[0].result.category == "open-redirect"


async def test_kind_select_toggles_category_specific_fields(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-validate"
        await pilot.pause()
        panel = app.query_one(ValidatePanel)
        assert panel.query_one("#va-cors-fields").display is False
        panel.query_one("#va-kind", Select).value = "cors"
        await pilot.pause()
        assert panel.query_one("#va-cors-fields").display is True
        assert panel.query_one("#va-idor-fields").display is False
