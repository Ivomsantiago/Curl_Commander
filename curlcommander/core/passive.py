"""Passive security analysis of a response (2.2).

Runs cheap, non-intrusive checks on any response: missing/weak security
headers, risky cookie flags, permissive CORS, verbose error leakage, and a
tech fingerprint. Everything is reported as a *candidate to investigate* —
never a claim of exploitation. This is value curl can never add, on every
request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from curlcommander.core.request_model import ResponseResult

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

# Body markers that indicate a leaked stack trace / verbose error.
_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "java.lang.",
    "at System.",
    "PHP Warning",
    "PHP Fatal error",
    "SQLSTATE",
    "ORA-0",
    "You have an error in your SQL syntax",
    "Microsoft OLE DB Provider",
    "Warning: include(",
)


@dataclass(frozen=True)
class Finding:
    severity: str  # high | medium | low | info
    category: str  # kebab-case slug
    title: str
    detail: str


def analyze(result: ResponseResult, url: str = "") -> list[Finding]:
    """Return passive findings for a response, most severe first."""
    findings: list[Finding] = []
    headers = {k.lower(): v for k, v in result.headers.items()}

    findings += _security_headers(headers, url)
    findings += _cookies(result.headers)
    findings += _cors(headers)
    findings += _verbose_errors(result.body)
    findings += _fingerprint(headers)

    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
    return findings


def _security_headers(headers: dict[str, str], url: str) -> list[Finding]:
    out: list[Finding] = []
    is_https = url.lower().startswith("https")
    checks = [
        (
            "content-security-policy",
            "medium",
            "CSP ausente",
            "Sem Content-Security-Policy: defesa em profundidade contra XSS ausente.",
        ),
        (
            "x-frame-options",
            "low",
            "X-Frame-Options ausente",
            "Sem X-Frame-Options/CSP frame-ancestors: possível clickjacking.",
        ),
        (
            "x-content-type-options",
            "low",
            "X-Content-Type-Options ausente",
            "Sem 'nosniff': o navegador pode adivinhar o Content-Type.",
        ),
        (
            "referrer-policy",
            "info",
            "Referrer-Policy ausente",
            "Sem Referrer-Policy: URLs podem vazar no cabeçalho Referer.",
        ),
    ]
    for name, sev, title, detail in checks:
        if name not in headers:
            out.append(Finding(sev, "security-headers", title, detail))
    if is_https and "strict-transport-security" not in headers:
        out.append(
            Finding("medium", "security-headers", "HSTS ausente", "Resposta HTTPS sem Strict-Transport-Security.")
        )
    return out


def _cookies(headers: dict[str, str]) -> list[Finding]:
    out: list[Finding] = []
    for key, value in headers.items():
        if key.lower() != "set-cookie":
            continue
        low = value.lower()
        name = value.split("=", 1)[0]
        missing = [
            flag
            for flag, tok in (("HttpOnly", "httponly"), ("Secure", "secure"), ("SameSite", "samesite"))
            if tok not in low
        ]
        if missing:
            out.append(
                Finding(
                    "low",
                    "cookie-flags",
                    f"Cookie sem flags: {name}",
                    f"O cookie '{name}' não tem: {', '.join(missing)}.",
                )
            )
    return out


def _cors(headers: dict[str, str]) -> list[Finding]:
    acao = headers.get("access-control-allow-origin")
    if acao is None:
        return []
    creds = headers.get("access-control-allow-credentials", "").lower() == "true"
    if acao == "*" and creds:
        return [
            Finding(
                "high",
                "cors",
                "CORS perigoso: * com credenciais",
                "Access-Control-Allow-Origin: * junto de Allow-Credentials: true é inseguro.",
            )
        ]
    if acao == "*":
        return [
            Finding(
                "medium",
                "cors",
                "CORS permissivo (*)",
                "Access-Control-Allow-Origin: * expõe a resposta a qualquer origem.",
            )
        ]
    return []


def _verbose_errors(body: str) -> list[Finding]:
    for marker in _ERROR_MARKERS:
        if marker in body:
            return [
                Finding(
                    "medium",
                    "verbose-error",
                    "Erro verboso / stack trace",
                    f"O corpo contém um indicador de erro detalhado: {marker!r}.",
                )
            ]
    return []


def _fingerprint(headers: dict[str, str]) -> list[Finding]:
    out: list[Finding] = []
    for name in ("server", "x-powered-by", "x-aspnet-version"):
        val = headers.get(name)
        if val and re.search(r"\d", val):
            out.append(Finding("info", "fingerprint", f"Fingerprint via {name}", f"{name}: {val}"))
    return out


def to_sarif(findings: list[Finding], url: str = "") -> dict[str, Any]:
    """A minimal SARIF 2.1.0 document for CI ingestion."""
    level = {"high": "error", "medium": "warning", "low": "warning", "info": "note"}
    results = [
        {
            "ruleId": f.category,
            "level": level.get(f.severity, "note"),
            "message": {"text": f"{f.title}: {f.detail}"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": url or "response"}}}],
        }
        for f in findings
    ]
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "CurlCommander", "rules": []}}, "results": results}],
    }
