"""Shared pytest configuration.

Windows event-loop policy fix (item 0): the default Proactor event loop on
Windows can leave socket transports pending at loop teardown, which surfaces as
a hung async test on CI (a `recv()` that never returns, orbiting the socket
tests). The Selector event loop does not exhibit this for our httpx/socket
usage, so pin it on Windows for the whole suite. This mirrors the fix many
asyncio projects apply and is a real root-cause change, not a timeout band-aid
(pytest-timeout is configured separately, only as a fast-fail diagnostic net).
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
