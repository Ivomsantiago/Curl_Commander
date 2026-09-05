"""Browser-executed XSS validation (H.2).

Moves a "reflected candidate" to CONFIRMED by opening it in a real browser: a
unique per-test canary marker avoids false positives from inert reflection, an
init script overrides the dialog functions and hooks common DOM sinks, and the
Playwright ``dialog`` event catches actual ``alert/prompt/confirm``. Covers
reflected, stored (navigate to the rendering page) and DOM-based XSS (which pure
HTTP testing cannot see).
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import quote

from curlcommander.core.browser import BrowserSession
from curlcommander.core.scope import ScopeError
from curlcommander.core.validators.base import (
    CONFIRMED,
    ERROR,
    NOT_VULNERABLE,
    REFLECTED,
    ValidationResult,
)

DEFAULT_MARKER = "§PAYLOAD§"

# Payload templates carrying the canary. {m} is the unique marker.
PAYLOAD_TEMPLATES = [
    "<script>alert('{m}')</script>",
    "\"><script>alert('{m}')</script>",
    "<img src=x onerror=alert('{m}')>",
    "'><svg onload=alert('{m}')>",
    "</title><script>alert('{m}')</script>",
    "<script>window['{m}']()</script>",
]

# Init script: define the canary fn and hook sinks so DOM-based execution that
# does not raise a dialog is still detected.
_INIT_SCRIPT = """
(() => {
  window.__cc = window.__cc || { hits: [], dialogs: [] };
  window['%CANARY%'] = function(){ window.__cc.hits.push('canary'); };
  const marker = '%CANARY%';
  try {
    const ow = document.write.bind(document);
    document.write = function(s){ if(String(s).indexOf(marker)>=0) window.__cc.hits.push('document.write'); return ow(s); };
  } catch(e){}
  try {
    const oe = window.eval;
    window.eval = function(s){ if(String(s).indexOf(marker)>=0) window.__cc.hits.push('eval'); return oe(s); };
  } catch(e){}
})();
"""


def _new_marker() -> str:
    return "cc" + secrets.token_hex(4)


async def validate_xss(
    session: BrowserSession,
    url_template: str,
    marker_token: str = DEFAULT_MARKER,
    templates: list[str] | None = None,
    screenshot_path: str | None = None,
) -> ValidationResult:
    """Try each payload in a browser; return CONFIRMED on execution.

    ``url_template`` must contain ``marker_token`` where the payload goes (e.g.
    ``https://t/search?q=§PAYLOAD§``). If it does not, the marker is appended as
    a query param.
    """
    canary = _new_marker()
    if marker_token not in url_template:
        sep = "&" if "?" in url_template else "?"
        url_template = f"{url_template}{sep}q={marker_token}"

    tmpls = templates or PAYLOAD_TEMPLATES
    reflected_hit: ValidationResult | None = None

    page = await session.new_page()
    dialogs: list[str] = []
    page.on("dialog", lambda d: _on_dialog(d, dialogs))
    await page.add_init_script(_INIT_SCRIPT.replace("%CANARY%", canary))

    try:
        for template in tmpls:
            payload = template.format(m=canary)
            url = url_template.replace(marker_token, quote(payload, safe=""))
            dialogs.clear()
            try:
                await session.goto(page, url)
                await page.wait_for_timeout(150)
            except ScopeError:
                raise  # out-of-scope must never be swallowed
            except Exception as exc:  # navigation/timeout for this payload only
                reflected_hit = reflected_hit or ValidationResult("xss", ERROR, url, str(exc), payload)
                continue

            hits = await _read_hits(page)
            executed = canary in "".join(dialogs) or bool(hits)
            if executed:
                if screenshot_path:
                    await page.screenshot(path=screenshot_path)
                return ValidationResult(
                    "xss",
                    CONFIRMED,
                    url,
                    detail=f"executed via {'dialog' if dialogs else hits}",
                    payload=payload,
                    evidence={"dialogs": list(dialogs), "sinks": hits, "canary": canary, "screenshot": screenshot_path},
                )

            content = await page.content()
            if payload in content and reflected_hit is None:
                reflected_hit = ValidationResult("xss", REFLECTED, url, "payload reflected unescaped", payload)

        return reflected_hit or ValidationResult("xss", NOT_VULNERABLE, url_template)
    finally:
        await page.close()


def _on_dialog(dialog: Any, sink: list[str]) -> None:
    sink.append(dialog.message)
    # Dismiss so navigation is not blocked; fire-and-forget.
    import asyncio

    asyncio.create_task(dialog.dismiss())


async def _read_hits(page: Any) -> list[str]:
    try:
        return list(await page.evaluate("window.__cc ? window.__cc.hits : []"))
    except Exception:
        return []
