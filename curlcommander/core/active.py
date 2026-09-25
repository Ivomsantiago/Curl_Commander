"""Active security scanner (per-parameter, heuristic).

Sends crafted payloads into each injectable parameter — one at a time, keeping
the others at their baseline value — so a finding names the exact parameter and
payload. Covers reflected XSS, error-based SQLi, SSTI, path traversal and open
redirect. Every check is a heuristic (reported with a confidence), never a
guarantee; confirm high-value hits with the browser validators (`validate`).

Pure and transport-mockable: everything routes through :func:`http_client.send`,
so the whole scanner is unit-testable with ``respx``.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from curlcommander.core.http_client import send
from curlcommander.core.passive import Finding
from curlcommander.core.request_model import RequestConfig, ResponseResult

# A sender seam so tests can inject a fake transport without patching globals.
Sender = Callable[[RequestConfig], Awaitable[ResponseResult]]

# SQL error signatures across common engines.
_SQL_ERRORS = (
    "SQL syntax",
    "mysql_fetch",
    "you have an error in your sql",
    "ORA-",
    "PostgreSQL query failed",
    "SQLite3::",
    "sqlite3.OperationalError",
    "Unclosed quotation mark",
    "Microsoft OLE DB Provider",
    "org.hibernate",
)

# Parameter names that commonly carry a redirect target.
_REDIRECT_HINTS = ("next", "url", "redirect", "return", "returnurl", "dest", "destination", "continue", "r", "u")


@dataclass(frozen=True)
class Injectable:
    """One place a payload can go: a query or form-body parameter."""

    location: str  # "query" | "form"
    name: str


def _injectables(config: RequestConfig) -> list[Injectable]:
    out: list[Injectable] = []
    query = urlsplit(config.url).query
    for name, _ in parse_qsl(query, keep_blank_values=True):
        out.append(Injectable("query", name))
    if config.body_type == "form" and config.body:
        for name, _ in parse_qsl(config.body, keep_blank_values=True):
            out.append(Injectable("form", name))
    # De-dupe while preserving order (a param can legitimately repeat).
    seen: set[tuple[str, str]] = set()
    uniq: list[Injectable] = []
    for inj in out:
        key = (inj.location, inj.name)
        if key not in seen:
            seen.add(key)
            uniq.append(inj)
    return uniq


def _mutate(config: RequestConfig, inj: Injectable, value: str) -> RequestConfig:
    """Return a copy of ``config`` with ``inj`` set to ``value`` (others intact)."""
    data = config.to_dict()
    if inj.location == "query":
        parts = urlsplit(config.url)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        new_pairs = [(k, value if k == inj.name else v) for k, v in pairs]
        data["url"] = urlunsplit(parts._replace(query=urlencode(new_pairs)))
    else:  # form
        pairs = parse_qsl(config.body, keep_blank_values=True)
        new_pairs = [(k, value if k == inj.name else v) for k, v in pairs]
        data["body"] = urlencode(new_pairs)
    return RequestConfig.from_dict(data)


def _canary() -> str:
    """A short, unique, alnum token unlikely to occur naturally in a response."""
    return "cc" + secrets.token_hex(4)


async def _probe(config: RequestConfig, inj: Injectable, value: str, sender: Sender) -> ResponseResult | None:
    try:
        return await sender(_mutate(config, inj, value))
    except Exception:
        return None


async def _check_param(config: RequestConfig, inj: Injectable, sender: Sender) -> list[Finding]:
    findings: list[Finding] = []
    where = f"parâmetro {inj.name!r} ({inj.location})"

    # 1) Reflected XSS — a unique markup canary reflected verbatim (unencoded).
    token = _canary()
    xss_value = f"{token}<x>"
    res = await _probe(config, inj, xss_value, sender)
    if res and res.body and xss_value in res.body:
        findings.append(
            Finding("high", "active-xss", "XSS refletido", f"Markup injetado refletido sem escape no {where}.")
        )

    # 2) Error-based SQLi — a lone quote provokes a database error.
    res = await _probe(config, inj, "'", sender)
    if res and res.body:
        low = res.body.lower()
        if any(sig.lower() in low for sig in _SQL_ERRORS):
            findings.append(
                Finding("high", "active-sqli", "SQL Injection (baseada em erro)", f"Erro de SQL revelado pelo {where}.")
            )

    # 3) SSTI — arithmetic evaluated server-side (canary + 7*7 → canary49).
    token = _canary()
    for expr in (f"{token}${{{{7*7}}}}", f"{token}{{{{7*7}}}}", f"{token}#{{7*7}}"):
        res = await _probe(config, inj, expr, sender)
        if res and res.body and f"{token}49" in res.body:
            findings.append(
                Finding(
                    "high", "active-ssti", "SSTI (template injection)", f"Expressão avaliada no servidor pelo {where}."
                )
            )
            break

    # 4) Path traversal — a classic payload surfacing /etc/passwd.
    res = await _probe(config, inj, "../../../../../../etc/passwd", sender)
    if res and res.body and "root:x:0:0" in res.body:
        findings.append(Finding("high", "active-traversal", "Path traversal", f"Leitura de /etc/passwd via {where}."))

    # 5) Open redirect — only for redirect-shaped params; a 3xx to our host.
    if inj.name.lower() in _REDIRECT_HINTS:
        marker = "https://curlcommander.example/"
        cfg = _mutate(config, inj, marker)
        cfg.follow_redirects = False
        try:
            res = await sender(cfg)
        except Exception:
            res = None
        if res and res.status_code and 300 <= res.status_code < 400:
            location = res.headers.get("location") or res.headers.get("Location") or ""
            if location.startswith(marker):
                findings.append(
                    Finding("medium", "active-open-redirect", "Open redirect", f"Redirecionamento externo via {where}.")
                )

    return findings


async def active_scan(config: RequestConfig, sender: Sender | None = None, max_params: int = 25) -> list[Finding]:
    """Run active heuristic checks against every injectable parameter.

    ``sender`` defaults to the real HTTP client; tests pass a fake. At most
    ``max_params`` parameters are probed so a huge query string can't fan out
    unbounded.
    """
    tx = sender or send
    injectables = _injectables(config)[:max_params]
    findings: list[Finding] = []
    for inj in injectables:
        findings.extend(await _check_param(config, inj, tx))
    # De-dupe identical findings (same category + title), most severe first.
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    seen: set[tuple[str, str, str]] = set()
    uniq: list[Finding] = []
    for f in findings:
        key = (f.severity, f.category, f.title)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    uniq.sort(key=lambda f: order.get(f.severity, 9))
    return uniq
