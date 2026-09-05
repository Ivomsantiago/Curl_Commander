"""CSRF PoC validation (H.3).

Builds an auto-submitting cross-site form to a state-changing endpoint and
submits it from a real (optionally authenticated) browser session. CONFIRMED
when the response shows the effect (a caller-supplied success marker); otherwise
the response is returned for the analyst to judge.
"""

from __future__ import annotations

import html

from curlcommander.core.browser import BrowserSession
from curlcommander.core.validators.base import CONFIRMED, REFLECTED, ValidationResult


def build_poc_html(action: str, method: str = "POST", fields: dict[str, str] | None = None) -> str:
    inputs = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">' for k, v in (fields or {}).items()
    )
    return (
        "<!doctype html><html><body>"
        f'<form id="f" action="{html.escape(action)}" method="{html.escape(method)}">{inputs}</form>'
        '<script>document.getElementById("f").submit()</script>'
        "</body></html>"
    )


async def validate_csrf(
    session: BrowserSession,
    action: str,
    method: str = "POST",
    fields: dict[str, str] | None = None,
    success_contains: str | None = None,
    screenshot_path: str | None = None,
) -> ValidationResult:
    session._enforce(action)
    page = await session.new_page()
    try:
        await page.set_content(build_poc_html(action, method, fields))
        try:
            await page.wait_for_load_state("networkidle")
        except Exception:
            await page.wait_for_timeout(500)
        content = await page.content()
        if screenshot_path:
            await page.screenshot(path=screenshot_path)

        if success_contains and success_contains in content:
            return ValidationResult(
                "csrf",
                CONFIRMED,
                action,
                "cross-site form submission took effect",
                evidence={"success_marker": success_contains, "screenshot": screenshot_path},
            )
        return ValidationResult(
            "csrf",
            REFLECTED,
            action,
            "form submitted cross-site; verify the effect manually",
            evidence={"final_url": page.url, "screenshot": screenshot_path},
        )
    finally:
        await page.close()
