"""Clickjacking validation (H.3).

Frames the target inside an attacker page in a real browser and checks whether
it actually renders (i.e. is not blocked by X-Frame-Options / CSP
frame-ancestors). CONFIRMED with a screenshot of the target inside the iframe.
"""

from __future__ import annotations

from typing import Any

from curlcommander.core.browser import BrowserSession
from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE, ValidationResult

_ATTACKER_PAGE = (
    "<!doctype html><html><body><h1>clickjacking PoC</h1>"
    '<iframe id="t" src="%URL%" width="800" height="600"></iframe>'
    "</body></html>"
)


async def validate_clickjacking(
    session: BrowserSession,
    url: str,
    screenshot_path: str | None = None,
) -> ValidationResult:
    session._enforce(url)  # scope check before loading the target in a frame
    page = await session.new_page()
    try:
        await page.set_content(_ATTACKER_PAGE.replace("%URL%", url))
        await page.wait_for_timeout(400)

        framed = await _frame_rendered(page, url)
        if framed:
            if screenshot_path:
                await page.screenshot(path=screenshot_path)
            return ValidationResult(
                "clickjacking",
                CONFIRMED,
                url,
                "target renders inside a cross-origin iframe (missing X-Frame-Options/frame-ancestors)",
                evidence={"screenshot": screenshot_path},
            )
        return ValidationResult(
            "clickjacking",
            NOT_VULNERABLE,
            url,
            "framing blocked (X-Frame-Options or CSP frame-ancestors present)",
        )
    finally:
        await page.close()


async def _frame_rendered(page: Any, url: str) -> bool:
    """True if the child frame actually navigated to the target and has content."""
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            if frame.url and url.split("?")[0] in frame.url:
                body = await frame.evaluate("document.body ? document.body.innerText.length : 0")
                return bool(body)
        except Exception:
            continue
    return False
