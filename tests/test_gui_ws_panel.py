"""Tests for the GUI WebSocket tab (item 9.5) — a fake WSClient stands in for
a real server, the same way test_ws_client.py fakes the `websockets` library
for the CLI's `ws connect`/`ws fuzz`."""

from textual.widgets import Button, Input, RichLog, Static

from curlcommander.gui.app import CurlCommanderApp
from curlcommander.gui.ws_panel import WSPanel


def _log_text(log: RichLog) -> str:
    return "\n".join(strip.text for strip in log.lines)


def _static_text(static: Static) -> str:
    return str(static._Static__content)  # noqa: SLF001 - no public accessor for Static's content


class _FakeResult:
    def __init__(self, body: str = "", error: str | None = None) -> None:
        self.body = body
        self.error = error


class _FakeClient:
    def __init__(self, url: str, **kwargs) -> None:
        self.url = url
        self.connected = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True

    async def send_message(self, message: str) -> _FakeResult:
        return _FakeResult(body=f"echo:{message}")


async def test_ws_connect_send_and_receive(tmp_path, monkeypatch):
    import curlcommander.core.ws_client as ws_client_mod

    monkeypatch.setattr(ws_client_mod, "WSClient", _FakeClient)
    monkeypatch.setattr(ws_client_mod, "ws_available", lambda: True)

    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-ws"
        await pilot.pause()
        panel = app.query_one(WSPanel)
        panel.query_one("#ws-url", Input).value = "ws://target/socket"
        panel.query_one("#ws-connect", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "conectado" in _static_text(panel.query_one("#ws-status", Static))

        panel.query_one("#ws-message", Input).value = "hello"
        panel.query_one("#ws-send", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert "hello" in _log_text(panel.query_one("#ws-sent", RichLog))
        assert "echo:hello" in _log_text(panel.query_one("#ws-recv", RichLog))


async def test_ws_send_without_connecting_is_refused(tmp_path):
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-ws"
        await pilot.pause()
        panel = app.query_one(WSPanel)
        panel.query_one("#ws-message", Input).value = "hello"
        panel.query_one("#ws-send", Button).press()
        await pilot.pause()
        assert "conecte" in _static_text(panel.query_one("#ws-status", Static)).lower()


async def test_ws_missing_extra_shows_clear_message(tmp_path, monkeypatch):
    import curlcommander.core.ws_client as ws_client_mod

    monkeypatch.setattr(ws_client_mod, "ws_available", lambda: False)
    app = CurlCommanderApp(db_path=str(tmp_path / "h.db"))
    async with app.run_test() as pilot:
        app.query_one("#main-tabs").active = "tab-ws"
        await pilot.pause()
        panel = app.query_one(WSPanel)
        panel.query_one("#ws-url", Input).value = "ws://target/socket"
        panel.query_one("#ws-connect", Button).press()
        await pilot.pause()
        status = _static_text(panel.query_one("#ws-status", Static)).lower()
        assert "curlcmd setup" in status or "extra" in status
