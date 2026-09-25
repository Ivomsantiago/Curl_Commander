"""In-process intercepting proxy controller for the graphical GUI.

Runs the mitmproxy-backed intercepting proxy (``core.proxy``) in a background
thread with its own event loop, and bridges it to the threaded web server:

* the web API starts/stops the proxy and toggles interception;
* while interception is on, each in-scope flow is *held* (its coroutine parked
  on an ``asyncio.Event``) and a JSON snapshot is queued for the browser UI;
* the UI forwards (optionally with an edited body), or drops, each held flow.

mitmproxy is imported lazily (the ``[proxy]`` extra), so importing this module
never requires it. The queue bookkeeping and the flow-mutation step are split
into plain functions so they are unit-testable with a fake flow, without the
extra installed.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class _Held:
    flow: Any
    event: Any  # asyncio.Event
    is_request: bool
    snapshot: dict[str, Any]


def snapshot_flow(flow: Any, is_request: bool, fid: str) -> dict[str, Any]:
    """A JSON-able view of a mitmproxy flow at the request or response stage."""
    req = flow.request
    if is_request:
        body = req.get_text(strict=False) if req.content else ""
        return {
            "id": fid,
            "direction": "request",
            "method": req.method,
            "url": req.url,
            "headers": dict(req.headers),
            "body": body or "",
        }
    resp = flow.response
    body = (resp.get_text(strict=False) if resp and resp.content else "") if resp else ""
    return {
        "id": fid,
        "direction": "response",
        "status": resp.status_code if resp else None,
        "url": req.url,
        "headers": dict(resp.headers) if resp else {},
        "body": body or "",
    }


def apply_resolution(held: _Held, action: str, body: str | None) -> None:
    """Mutate a held flow to forward (optionally edited) or drop it.

    Pure with respect to threading — the caller schedules it on the proxy loop.
    ``body`` replaces the request or response content when forwarding; ``None``
    leaves it untouched.
    """
    if action == "drop":
        held.flow.kill()
        return
    if body is not None:
        if held.is_request:
            held.flow.request.content = body.encode()
        elif held.flow.response is not None:
            held.flow.response.content = body.encode()


class InterceptController:
    """Owns the background proxy and the intercept queue for the web GUI."""

    def __init__(
        self,
        repo: Any = None,
        engagement: str = "",
        scope_entries: list[str] | None = None,
        scope_provider: Any = None,
    ) -> None:
        self.repo = repo
        self.engagement = engagement
        # ``scope_provider`` (a zero-arg callable) is read at start() so the
        # proxy honours a scope the user edited in the GUI *after* the server
        # started; ``scope_entries`` is the static fallback used by tests.
        self._scope_provider = scope_provider
        self.scope_entries = scope_entries or []
        self.port = 8080
        self.running = False
        self.intercept_enabled = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._master: Any = None
        self._held: dict[str, _Held] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._error: str | None = None

    # -- availability -------------------------------------------------------

    @staticmethod
    def available() -> bool:
        from curlcommander.core import proxy as pm

        return pm.proxy_available()

    def _refresh_scope(self) -> None:
        """Pull the current scope from the provider (GUI edits win over startup)."""
        if self._scope_provider is not None:
            self.scope_entries = list(self._scope_provider())

    # -- lifecycle ----------------------------------------------------------

    def start(self, port: int = 8080) -> None:
        from curlcommander.core import proxy as pm

        pm.require_proxy()
        if self.running:
            return
        self._refresh_scope()  # the user may have edited scope in the GUI
        self.port = port
        self._error = None
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), name="curlcmd-webproxy", daemon=True)
        self._thread.start()
        ready.wait(timeout=10)
        self.running = self._error is None

    def _run(self, ready: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._serve(ready))
        except Exception as exc:  # noqa: BLE001
            self._error = f"{type(exc).__name__}: {exc}"
            ready.set()
        finally:
            self.running = False
            loop.close()

    async def _serve(self, ready: threading.Event) -> None:
        from mitmproxy.options import Options
        from mitmproxy.tools.dump import DumpMaster

        from curlcommander.core import proxy as pm

        opts = Options(listen_host="127.0.0.1", listen_port=self.port, confdir=str(pm.ca_dir()))
        ignore = pm.ignore_hosts_regex(self.scope_entries)
        if ignore:
            opts.update(ignore_hosts=[ignore])  # type: ignore[no-untyped-call]
        master = DumpMaster(opts)
        master.addons.add(  # type: ignore[no-untyped-call]
            pm.build_addon(self.scope_entries, [], self.repo, self.engagement, self._hook)
        )
        self._master = master
        ready.set()
        await master.run()

    def stop(self) -> None:
        # Release every held flow, then shut the master down on its own loop.
        with self._lock:
            held = list(self._held.values())
            self._held.clear()
            self._order.clear()
        for h in held:
            self._resolve_on_loop(h, "drop", None)
        if self._loop and self._master:
            self._loop.call_soon_threadsafe(self._master.shutdown)
        self.running = False
        self.intercept_enabled = False

    # -- interception -------------------------------------------------------

    def set_intercept(self, on: bool) -> None:
        self.intercept_enabled = on
        if not on:
            self.forward_all()

    async def _hook(self, flow: Any, is_request: bool) -> None:
        if not self.intercept_enabled:
            return
        fid = uuid.uuid4().hex[:8]
        event = asyncio.Event()
        snap = snapshot_flow(flow, is_request, fid)
        with self._lock:
            self._held[fid] = _Held(flow, event, is_request, snap)
            self._order.append(fid)
        await event.wait()

    def queue(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._held[fid].snapshot for fid in self._order if fid in self._held]

    def resolve(self, fid: str, action: str, body: str | None = None) -> bool:
        with self._lock:
            held = self._held.pop(fid, None)
            if fid in self._order:
                self._order.remove(fid)
        if held is None:
            return False
        self._resolve_on_loop(held, action, body)
        return True

    def forward_all(self) -> None:
        with self._lock:
            held = list(self._held.values())
            self._held.clear()
            self._order.clear()
        for h in held:
            self._resolve_on_loop(h, "forward", None)

    def _resolve_on_loop(self, held: _Held, action: str, body: str | None) -> None:
        def _do() -> None:
            apply_resolution(held, action, body)
            held.event.set()

        if self._loop is not None:
            self._loop.call_soon_threadsafe(_do)
        else:  # no loop (tests): apply inline
            _do()

    # -- status / browser ---------------------------------------------------

    def status(self) -> dict[str, Any]:
        from curlcommander.core import proxy as pm

        return {
            "available": self.available(),
            "running": self.running,
            "intercept": self.intercept_enabled,
            "port": self.port,
            "queued": len(self._order),
            "ca_cert": str(pm.ca_cert_path()) if self.available() else None,
            "error": self._error,
        }

    def launch_browser(self, engine: str = "chromium", channel: str | None = None) -> None:
        """Open a browser routed through the running proxy, on the proxy loop."""
        if not self.running or self._loop is None:
            raise RuntimeError("proxy não está rodando")
        from curlcommander.core.proxy import _launch_browser_through

        future = asyncio.run_coroutine_threadsafe(
            _launch_browser_through(self.port, self.scope_entries, engine=engine, channel=channel),
            self._loop,
        )
        # Wait for the launch to actually happen so a failure (missing Playwright
        # browser, invalid channel) surfaces to the caller instead of a false
        # "launched": true.
        future.result(timeout=60)
