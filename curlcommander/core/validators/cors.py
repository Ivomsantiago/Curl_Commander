"""CORS misconfiguration validation (H.3).

Sends a cross-origin request with a malicious Origin and reports the
Access-Control-* response. CONFIRMED when the server reflects the attacker
origin (or allows ``*``) AND allows credentials — the combination that lets a
malicious page read authenticated responses.
"""

from __future__ import annotations

import httpx

from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE, ValidationResult


async def validate_cors(
    url: str,
    origin: str = "https://evil.example",
    verify_ssl: bool = True,
    timeout: float = 30.0,
) -> ValidationResult:
    async with httpx.AsyncClient(verify=verify_ssl, timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Origin": origin})

    acao = resp.headers.get("access-control-allow-origin", "")
    acac = resp.headers.get("access-control-allow-credentials", "").lower() == "true"
    evidence = {"origin": origin, "acao": acao, "acac": acac, "status": resp.status_code}

    reflects = acao == origin or acao == "*"
    if reflects and acac and acao != "*":
        # Reflected origin + credentials = readable authenticated response.
        return ValidationResult("cors", CONFIRMED, url, "origin reflected with credentials", origin, evidence)
    if reflects:
        detail = "wildcard ACAO" if acao == "*" else "origin reflected (no credentials)"
        return ValidationResult("cors", "REFLECTED", url, detail, origin, evidence)
    return ValidationResult("cors", NOT_VULNERABLE, url, "origin not allowed", origin, evidence)
