"""IDOR / BOLA workflow: authorization correlation across two identities.

This is a fundamentally different test from fuzzing: not "which payload breaks
the response" but "does the same resource respond differently depending on WHO
authenticates". For each resource id, the exact same request is sent as identity
A (the baseline owner) and as identity B (the attacker); only the auth changes.

A raw ``200`` from B does not mean vulnerable — RESTful APIs legitimately return
structurally similar JSON for different resources — so we compare body structure
with ``difflib.SequenceMatcher`` against A's response and treat the middle ground
as ``suspect`` (needs a human), never an automatic "confirmed".
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from curlcommander.core.fuzzer import FuzzResult, run_fuzz, substitute
from curlcommander.core.http_client import send
from curlcommander.core.request_model import RequestConfig, ResponseResult

if TYPE_CHECKING:
    from curlcommander.core.auth_macro import AuthMacro

_MARKER = "RESOURCE_ID"

CONFIRMED = "confirmed"
BLOCKED = "blocked"
SUSPECT = "suspect"


@dataclass
class IDORFinding:
    resource_id: str
    status_a: int | None
    status_b: int | None
    similarity: float
    verdict: str
    note: str = ""


async def _apply_send(cfg: RequestConfig, auth: AuthMacro | None, env: dict[str, str] | None) -> ResponseResult:
    if auth is None:
        return await send(cfg)
    await auth.ensure(env)
    return await send(auth.apply(cfg))


async def check_idor(
    template: RequestConfig,
    ids: list[str],
    auth_a: AuthMacro | None,
    auth_b: AuthMacro | None,
    threshold: float = 0.85,
    env: dict[str, str] | None = None,
) -> list[IDORFinding]:
    """Send each resource id as A (owner) and B (attacker); classify the diff."""
    findings: list[IDORFinding] = []
    for rid in ids:
        cfg = substitute(template, {_MARKER: rid})
        res_a = await _apply_send(cfg, auth_a, env)
        res_b = await _apply_send(cfg, auth_b, env)
        ratio = SequenceMatcher(None, res_a.body, res_b.body).ratio()
        findings.append(_classify(rid, res_a.status_code, res_b.status_code, ratio, threshold))
    return findings


def _classify(rid: str, status_a: int | None, status_b: int | None, ratio: float, threshold: float) -> IDORFinding:
    # B sees what A sees: same resource returned to a different identity.
    if status_a == 200 and status_b == 200 and ratio >= threshold:
        return IDORFinding(
            rid,
            status_a,
            status_b,
            ratio,
            CONFIRMED,
            note="B recebeu 200 com corpo estruturalmente igual ao de A — confirme que o recurso não é de B.",
        )
    # Access control appears to be working for B.
    if status_b in (401, 403, 404):
        return IDORFinding(rid, status_a, status_b, ratio, BLOCKED, note="B foi barrado (controle de acesso ativo).")
    # Everything else needs a human.
    return IDORFinding(
        rid,
        status_a,
        status_b,
        ratio,
        SUSPECT,
        note="Meio-termo: status/corpo não conclusivos — precisa de análise humana.",
    )


async def enumerate_range(
    template: RequestConfig,
    start: int,
    end: int,
    auth: AuthMacro | None = None,
    concurrency: int = 20,
    env: dict[str, str] | None = None,
) -> list[FuzzResult]:
    """Horizontal enumeration: one identity, a sequential id range (reuses the fuzzer).

    Turns a confirmed IDOR into "how many records can I actually reach?" — the
    number that matters in an impact report.
    """
    marked = substitute(template, {_MARKER: "FUZZ"})
    wordlist = [str(i) for i in range(start, end + 1)]
    return await run_fuzz(marked, [wordlist], concurrency=concurrency, auth=auth, env=env)
