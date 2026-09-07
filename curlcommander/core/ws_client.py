"""WebSocket transport for the fuzzer + an interactive client (extra ``ws``).

The ``websockets`` package is an optional dependency, imported lazily so the
base install never requires it. :func:`ws_available`/:func:`require_ws` follow
the same degrade-with-a-clear-message pattern as ``browser``/``proxy``/``oob``.

The key design point (item 5) is that fuzzing logic is **not** duplicated: a
:class:`WSClient` exposes a ``transport`` compatible with
``fuzzer.run_fuzz(transport=…)``, so clusterbomb/pitchfork combination,
filters and anomaly flagging are reused unchanged. Each fuzz payload is sent as
one WebSocket message and the next inbound frame is wrapped as a
``ResponseResult`` (synthetic status ``101`` on a reply, ``None`` on
error/timeout).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from curlcommander.core.request_model import RequestConfig, ResponseResult

if TYPE_CHECKING:
    from curlcommander.core.fuzzer import Transport


class WSError(RuntimeError):
    """WebSocket transport failure with a humanised message."""


def ws_available() -> bool:
    try:
        import websockets  # noqa: F401
    except ImportError:
        return False
    return True


def require_ws() -> None:
    if not ws_available():
        from curlcommander.core import features

        raise WSError(features.missing_message("ws"))


# Synthetic status codes so the fuzzer's (status, size) baseline still works for
# WebSocket traffic, which has no per-message HTTP status.
_WS_OK = 101  # a reply was received
_WS_TIMEOUT = None  # no reply within the read window / transport error


class WSClient:
    """A single WebSocket connection usable as a fuzzer transport.

    Sends are serialised with a lock so that, under the fuzzer's concurrency,
    each payload is paired with the very next inbound frame (request/response
    correlation over a single socket).
    """

    def __init__(self, url: str, *, read_timeout: float = 10.0, extra_headers: list[tuple[str, str]] | None = None):
        self.url = url
        self.read_timeout = read_timeout
        self.extra_headers = extra_headers or []
        self._ws: Any = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> WSClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def connect(self) -> None:
        require_ws()
        import websockets

        try:
            # websockets>=12 accepts additional_headers; older took extra_headers.
            kwargs: dict[str, Any] = {}
            if self.extra_headers:
                kwargs["additional_headers"] = self.extra_headers
            self._ws = await websockets.connect(self.url, **kwargs)
        except TypeError:
            self._ws = await websockets.connect(self.url, extra_headers=self.extra_headers)
        except Exception as exc:  # noqa: BLE001 - normalise connect failures
            raise WSError(f"não foi possível conectar em {self.url}: {exc}") from exc

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    async def send_message(self, message: str) -> ResponseResult:
        if self._ws is None:
            raise WSError("WebSocket não conectado")
        t0 = time.monotonic()
        async with self._lock:
            try:
                await self._ws.send(message)
                reply = await asyncio.wait_for(self._ws.recv(), timeout=self.read_timeout)
            except TimeoutError:
                return self._result("", t0, error="timeout: sem resposta do servidor", status=_WS_TIMEOUT)
            except Exception as exc:  # noqa: BLE001 - connection closed mid-fuzz, etc.
                return self._result("", t0, error=str(exc), status=_WS_TIMEOUT)
        body = reply.decode("utf-8", "replace") if isinstance(reply, bytes) else str(reply)
        return self._result(body, t0, error=None, status=_WS_OK)

    @staticmethod
    def _result(body: str, t0: float, *, error: str | None, status: int | None) -> ResponseResult:
        content = body.encode("utf-8", "replace")
        return ResponseResult(
            status_code=status,
            reason="WS",
            headers={},
            body=body,
            content_type="application/websocket",
            duration_ms=(time.monotonic() - t0) * 1000.0,
            size_bytes=len(content),
            error=error,
            content=content,
        )

    def transport(self) -> Transport:
        """A fuzzer transport that sends each request's body as a WS message."""

        async def _t(cfg: RequestConfig) -> ResponseResult:
            return await self.send_message(cfg.body)

        return _t
