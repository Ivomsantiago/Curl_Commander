"""Active security analysis (heuristics)."""

from __future__ import annotations

from curlcommander.core.http_client import send
from curlcommander.core.passive import Finding
from curlcommander.core.request_model import RequestConfig


async def active_scan(config: RequestConfig) -> list[Finding]:
    """Run active heuristic checks by sending modified requests."""
    findings: list[Finding] = []
    original_url = config.url

    if "?" not in original_url:
        return findings

    # Heuristic 1: XSS Reflected (Basic)
    xss_payload = "<script>alert(1)</script>"
    # Simple replace of all param values with payload
    url_base, query = original_url.split("?", 1)
    new_query = "&".join(f"{k}={xss_payload}" for k in (p.split("=")[0] for p in query.split("&") if p))
    xss_url = f"{url_base}?{new_query}"

    xss_config = RequestConfig(**{**config.to_dict(), "url": xss_url, "body_type": "none", "body": ""})
    try:
        res = await send(xss_config)
        if res.status_code == 200 and xss_payload in res.body:
            findings.append(
                Finding(
                    "high",
                    "active-xss",
                    "XSS Refletido",
                    "O payload de XSS foi refletido sem sanitização no corpo da resposta.",
                )
            )
    except Exception:
        pass

    # Heuristic 2: Error-Based SQLi
    sqli_payload = "'"
    new_query_sqli = "&".join(f"{k}={sqli_payload}" for k in (p.split("=")[0] for p in query.split("&") if p))
    sqli_url = f"{url_base}?{new_query_sqli}"
    sqli_config = RequestConfig(**{**config.to_dict(), "url": sqli_url, "body_type": "none", "body": ""})

    try:
        res = await send(sqli_config)
        if any(marker in res.body for marker in ("SQL syntax", "mysql_fetch", "ORA-", "PostgreSQL query failed")):
            findings.append(
                Finding(
                    "high", "active-sqli", "SQL Injection", "Sintaxe SQL inválida revelou um erro de banco de dados."
                )
            )
    except Exception:
        pass

    return findings
