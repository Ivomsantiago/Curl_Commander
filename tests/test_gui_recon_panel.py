"""Tests for the GUI Recon & Discovery tab (item 9.2) — the
subfinder -> httpx -> nuclei pipeline over core.recon.scan.run_and_stream,
faked the same way tests/test_recon.py does for the CLI's `recon` subcommand.
"""

from textual.widgets import Button, Input, Static, Tree

from curlcommander.core.recon import scan
from curlcommander.core.recon.tools import ReconToolError
from curlcommander.gui.app import CurlCommanderApp
from curlcommander.gui.recon_panel import ReconPanel


def _static_text(static: Static) -> str:
    return str(static._Static__content)  # noqa: SLF001 - no public accessor for Static's content


async def _fake_pipeline(name, args):
    if name == "subfinder":
        yield {"host": "api.target.com"}
    elif name == "httpx":
        yield {"url": "https://api.target.com/", "status_code": 200, "title": "API", "host": "api.target.com"}
    else:  # nuclei
        yield {
            "template-id": "exposed-panel",
            "info": {"severity": "high", "name": "Exposed admin panel"},
            "matched-at": "https://api.target.com/",
        }


async def test_recon_pipeline_populates_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "run_and_stream", _fake_pipeline)
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-recon"
        await pilot.pause()
        panel = app.query_one(ReconPanel)
        panel.query_one("#rp-domain", Input).value = "target.com"
        panel.query_one("#rp-run", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        status = _static_text(panel.query_one("#rp-status", Static))
        assert "1 subdomínio" in status
        assert "1 vivo" in status
        assert "1 achado" in status

        tree = panel.query_one("#rp-tree", Tree)
        host_node = tree.root.children[0]
        assert "api.target.com" in str(host_node.label)
        url_node = host_node.children[0]
        assert url_node.data == "https://api.target.com/"
        finding_node = url_node.children[0]
        assert "HIGH" in str(finding_node.label)


async def test_recon_missing_binary_shows_clear_message_not_a_traceback(tmp_path, monkeypatch):
    async def fake_missing(name, args):
        raise ReconToolError(f"'{name}' não encontrado no PATH.")
        yield  # pragma: no cover - unreachable, keeps this an async generator

    monkeypatch.setattr(scan, "run_and_stream", fake_missing)
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-recon"
        await pilot.pause()
        panel = app.query_one(ReconPanel)
        panel.query_one("#rp-domain", Input).value = "target.com"
        panel.query_one("#rp-run", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        status = _static_text(panel.query_one("#rp-status", Static))
        assert "não encontrado" in status


async def test_recon_refuses_empty_domain(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-recon"
        await pilot.pause()
        panel = app.query_one(ReconPanel)
        panel.query_one("#rp-run", Button).press()
        await pilot.pause()
        assert "domínio" in _static_text(panel.query_one("#rp-status", Static)).lower()
