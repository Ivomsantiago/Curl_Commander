"""Optional Playwright browser layer (H.1).

Playwright is an optional extra: import failure degrades to a clear message,
never a hard dependency. Chromium is located from PLAYWRIGHT_BROWSERS_PATH or
CURLCOMMANDER_CHROMIUM when present (so a standalone binary can point at a
system Chromium), otherwise Playwright's own bundled browser is used. Every
navigation is scope-enforced.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

from curlcommander.core import scope
from curlcommander.core.headers import HeaderList


class BrowserError(RuntimeError):
    pass


def browser_available() -> bool:
    try:
        import playwright.async_api  # noqa: F401

        return True
    except Exception:
        return False


def require_browser() -> None:
    if not browser_available():
        raise BrowserError(
            "the browser feature needs the optional extra: pip install 'curlcommander[browser]' "
            "&& playwright install chromium"
        )


def chromium_executable() -> str | None:
    """Locate a Chromium binary, or None to let Playwright use its bundled one."""
    env = os.environ.get("CURLCOMMANDER_CHROMIUM")
    if env and Path(env).exists():
        return env
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if base:
        patterns = [
            "chromium-*/chrome-linux/chrome",
            "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-win/chrome.exe",
        ]
        for pat in patterns:
            hits = sorted(glob.glob(os.path.join(base, pat)))
            if hits:
                return hits[-1]
    return None


class BrowserSession:
    """Async context manager around a Chromium browser context."""

    def __init__(
        self,
        headless: bool = True,
        proxy: str | None = None,
        cookies: HeaderList | None = None,
        user_agent: str | None = None,
        scope_entries: list[str] | None = None,
        timeout_ms: int = 15000,
        har_path: str | None = None,
        trace_path: str | None = None,
    ) -> None:
        self.headless = headless
        self.proxy = proxy
        self.cookies = cookies
        self.user_agent = user_agent
        self.scope_entries = scope_entries or []
        self.timeout_ms = timeout_ms
        self.har_path = har_path
        self.trace_path = trace_path
        self._pw: Any = None
        self._browser: Any = None
        self.context: Any = None

    async def __aenter__(self) -> BrowserSession:
        require_browser()
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": self.headless}
        exe = chromium_executable()
        if exe:
            launch_kwargs["executable_path"] = exe
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}
        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        ctx_kwargs: dict[str, Any] = {"ignore_https_errors": True}
        if self.user_agent:
            ctx_kwargs["user_agent"] = self.user_agent
        if self.har_path:
            ctx_kwargs["record_har_path"] = self.har_path  # H.5: navigation HAR
        self.context = await self._browser.new_context(**ctx_kwargs)
        self.context.set_default_timeout(self.timeout_ms)
        if self.trace_path:
            await self.context.tracing.start(screenshots=True, snapshots=True)
        if self.cookies:
            await self._apply_cookies()
        return self

    async def __aexit__(self, *exc: object) -> None:
        try:
            if self.context and self.trace_path:
                await self.context.tracing.stop(path=self.trace_path)
            if self.context:
                await self.context.close()  # flushes the HAR
            if self._browser:
                await self._browser.close()
        finally:
            if self._pw:
                await self._pw.stop()

    async def _apply_cookies(self) -> None:
        entries = []
        for name, value in self.cookies or []:
            entries.append({"name": name, "value": value, "url": None})
        # Cookies need a URL/domain; applied per-navigation instead when unknown.
        self._pending_cookies = entries

    def _enforce(self, url: str) -> None:
        if self.scope_entries:
            scope.enforce(url, self.scope_entries)

    async def new_page(self) -> Any:
        return await self.context.new_page()

    async def goto(self, page: Any, url: str) -> Any:
        """Scope-enforced navigation."""
        self._enforce(url)
        if getattr(self, "_pending_cookies", None):
            from urllib.parse import urlsplit

            host = urlsplit(url).hostname
            if host:
                for c in self._pending_cookies:
                    c.pop("url", None)
                    c["domain"] = host
                    c["path"] = "/"
                await self.context.add_cookies(self._pending_cookies)
                self._pending_cookies = []
        return await page.goto(url, wait_until="load")
