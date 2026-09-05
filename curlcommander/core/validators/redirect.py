"""Open redirect validation (H.3).

Injects an attacker destination into a redirect parameter and follows the
redirect chain. CONFIRMED when the final URL lands on the attacker's host
(cross-origin) — proving the redirect target is attacker-controlled.
"""

from __future__ import annotations

from urllib.parse import quote, urlsplit

import httpx

from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE, ValidationResult

DEFAULT_MARKER = "§DEST§"
CANARY_HOST = "cc-oob.example"


async def validate_open_redirect(
    url_template: str,
    marker_token: str = DEFAULT_MARKER,
    canary_host: str = CANARY_HOST,
    verify_ssl: bool = True,
    timeout: float = 30.0,
) -> ValidationResult:
    """``url_template`` has ``marker_token`` where the redirect destination goes."""
    if marker_token not in url_template:
        sep = "&" if "?" in url_template else "?"
        url_template = f"{url_template}{sep}next={marker_token}"

    origin_host = urlsplit(url_template).hostname or ""
    # Try a few common bypass encodings of the attacker destination.
    destinations = [
        f"https://{canary_host}/",
        f"//{canary_host}/",
        f"https:/{canary_host}/",
    ]

    async with httpx.AsyncClient(verify=verify_ssl, timeout=timeout, follow_redirects=True) as client:
        for dest in destinations:
            url = url_template.replace(marker_token, quote(dest, safe=""))
            try:
                resp = await client.get(url)
            except httpx.RequestError:
                continue
            final_host = urlsplit(str(resp.url)).hostname or ""
            chain = [str(r.url) for r in resp.history] + [str(resp.url)]
            if final_host == canary_host and final_host != origin_host:
                return ValidationResult(
                    "open-redirect",
                    CONFIRMED,
                    url,
                    f"redirected off-site to {final_host}",
                    dest,
                    {"chain": chain, "final": str(resp.url)},
                )
    return ValidationResult("open-redirect", NOT_VULNERABLE, url_template)
