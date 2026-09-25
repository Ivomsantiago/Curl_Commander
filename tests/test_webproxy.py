"""Tests for the live-intercept proxy controller (core.webproxy).

Uses a fake mitmproxy flow so the queue/resolve/snapshot logic is exercised
without the [proxy] extra or a running proxy loop.
"""

import asyncio

from curlcommander.core import webproxy
from curlcommander.core.webproxy import InterceptController, _Held, apply_resolution, snapshot_flow


class _Req:
    def __init__(self):
        self.content = b"original body"
        self.method = "POST"
        self.url = "https://target.example/login"
        self.headers = {"Host": "target.example", "Content-Type": "text/plain"}

    def get_text(self, strict=False):
        return self.content.decode()


class _Resp:
    def __init__(self):
        self.content = b"<html>ok</html>"
        self.status_code = 200
        self.headers = {"Content-Type": "text/html"}

    def get_text(self, strict=False):
        return self.content.decode()


class _Flow:
    def __init__(self, with_response=False):
        self.request = _Req()
        self.response = _Resp() if with_response else None
        self.killed = False

    def kill(self):
        self.killed = True


def test_snapshot_request():
    snap = snapshot_flow(_Flow(), True, "abc")
    assert snap["direction"] == "request"
    assert snap["method"] == "POST"
    assert snap["url"].endswith("/login")
    assert snap["body"] == "original body"


def test_snapshot_response():
    snap = snapshot_flow(_Flow(with_response=True), False, "abc")
    assert snap["direction"] == "response"
    assert snap["status"] == 200
    assert "ok" in snap["body"]


def _held(flow, is_request=True):
    return _Held(flow, asyncio.Event(), is_request, snapshot_flow(flow, is_request, "id1"))


def test_apply_resolution_drop_kills():
    flow = _Flow()
    apply_resolution(_held(flow), "drop", None)
    assert flow.killed is True


def test_apply_resolution_forward_edits_request_body():
    flow = _Flow()
    apply_resolution(_held(flow), "forward", "tampered=1")
    assert flow.request.content == b"tampered=1"


def test_apply_resolution_forward_edits_response_body():
    flow = _Flow(with_response=True)
    apply_resolution(_held(flow, is_request=False), "forward", "<html>edited</html>")
    assert flow.response.content == b"<html>edited</html>"


def test_apply_resolution_forward_none_leaves_body():
    flow = _Flow()
    apply_resolution(_held(flow), "forward", None)
    assert flow.request.content == b"original body"


def test_controller_queue_and_resolve_without_loop():
    ctrl = InterceptController()
    flow = _Flow()
    held = _held(flow)
    ctrl._held["id1"] = held
    ctrl._order.append("id1")

    assert [s["id"] for s in ctrl.queue()] == ["id1"]
    assert ctrl.resolve("id1", "forward", "x=2") is True
    # Flow forwarded with the edit, event released, and removed from the queue.
    assert flow.request.content == b"x=2"
    assert held.event.is_set()
    assert ctrl.queue() == []


def test_controller_resolve_unknown_id():
    assert InterceptController().resolve("nope", "forward", None) is False


def test_controller_forward_all_clears_queue():
    ctrl = InterceptController()
    flows = [_Flow() for _ in range(3)]
    for i, f in enumerate(flows):
        ctrl._held[f"id{i}"] = _held(f)
        ctrl._order.append(f"id{i}")
    ctrl.forward_all()
    assert ctrl.queue() == []


def test_controller_status_shape():
    st = InterceptController(engagement="ENG").status()
    assert set(st) >= {"available", "running", "intercept", "port", "queued", "error"}
    assert st["running"] is False


def test_refresh_scope_reads_live_provider():
    live = ["a.example"]
    ctrl = InterceptController(scope_provider=lambda: live)
    ctrl._refresh_scope()
    assert ctrl.scope_entries == ["a.example"]
    # A later GUI edit replaces the list; the controller picks it up on refresh.
    live = ["b.example", "c.example"]
    ctrl = InterceptController(scope_provider=lambda: live)
    ctrl._refresh_scope()
    assert ctrl.scope_entries == ["b.example", "c.example"]


def test_available_matches_proxy(monkeypatch):
    from curlcommander.core import proxy as pm

    monkeypatch.setattr(pm, "proxy_available", lambda: False)
    assert webproxy.InterceptController.available() is False
