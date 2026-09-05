"""Content discovery (dirbusting) and a bug-bounty scan profile.

Both reuse the existing fuzz engine (`core/fuzzer`) rather than a second one:
discovery is a FUZZ over a URL path with response filters and optional shallow
recursion; bounty-scan chains discovery with per-category payload fuzzing and
consolidates candidates by severity.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from curlcommander.core.fuzzer import FuzzFilters, FuzzResult, run_fuzz
from curlcommander.core.request_model import RequestConfig


def expand_words(words: list[str], extensions: list[str] | None) -> list[str]:
    """Add extension variants (word, word.php, word.bak, ...)."""
    if not extensions:
        return words
    out: list[str] = []
    for w in words:
        out.append(w)
        for ext in extensions:
            ext = ext.lstrip(".")
            if ext:
                out.append(f"{w}.{ext}")
    return out


def _fuzz_url(base_url: str) -> str:
    if "FUZZ" in base_url:
        return base_url
    return base_url.rstrip("/") + "/FUZZ"


def _looks_like_dir(result: FuzzResult) -> bool:
    """A hit worth recursing into: success/redirect/forbidden, no extension."""
    if result.status_code not in (200, 201, 301, 302, 307, 401, 403):
        return False
    last = result.payloads[-1] if result.payloads else ""
    return "." not in last.rsplit("/", 1)[-1]


async def discover(
    base_url: str,
    words: list[str],
    extensions: list[str] | None = None,
    filters: FuzzFilters | None = None,
    concurrency: int = 20,
    rate: float = 0.0,
    recurse: int = 0,
    verify_ssl: bool = True,
    timeout: float = 30.0,
) -> list[FuzzResult]:
    """Run one or more levels of content discovery over *base_url*."""
    filters = filters or FuzzFilters(filter_codes={404})
    expanded = expand_words(words, extensions)

    async def one_level(url: str) -> list[FuzzResult]:
        cfg = RequestConfig(method="GET", url=_fuzz_url(url), verify_ssl=verify_ssl, timeout=timeout)
        return await run_fuzz(cfg, [expanded], filters=filters, concurrency=concurrency, rate=rate)

    results = await one_level(base_url)
    if recurse > 0:
        for hit in list(results):
            if _looks_like_dir(hit):
                child_base = base_url.rstrip("/") + "/" + hit.payloads[-1]
                child = await discover(
                    child_base,
                    words,
                    extensions=extensions,
                    filters=filters,
                    concurrency=concurrency,
                    rate=rate,
                    recurse=recurse - 1,
                    verify_ssl=verify_ssl,
                    timeout=timeout,
                )
                # Prefix child payloads with their parent path for readability.
                for c in child:
                    c.payloads = [hit.payloads[-1] + "/" + p for p in c.payloads]
                results.extend(child)
    return results


# --- bounty-scan ----------------------------------------------------------

# Rough severity ranking for consolidating candidates.
_SEVERITY = {
    "sqli": "high",
    "cmdi": "high",
    "ssti": "high",
    "traversal": "medium",
    "lfi": "medium",
    "ssrf": "medium",
    "xss": "medium",
    "redirect": "low",
}


@dataclass
class Candidate:
    category: str
    severity: str
    payload: str
    status_code: int | None
    size_bytes: int
    note: str = ""


@dataclass
class BountyReport:
    url: str
    discovered: list[FuzzResult] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)

    def by_severity(self) -> dict[str, list[Candidate]]:
        buckets: dict[str, list[Candidate]] = {"high": [], "medium": [], "low": []}
        for c in self.candidates:
            buckets.setdefault(c.severity, []).append(c)
        return buckets


async def category_fuzz(
    param_url: str,
    category: str,
    payloads: list[str],
    concurrency: int = 10,
    rate: float = 0.0,
    verify_ssl: bool = True,
    timeout: float = 30.0,
) -> list[FuzzResult]:
    """Fuzz a category's payloads into a FUZZ marker on *param_url*."""
    cfg = RequestConfig(method="GET", url=_fuzz_url(param_url), verify_ssl=verify_ssl, timeout=timeout)
    return await run_fuzz(cfg, [payloads], concurrency=concurrency, rate=rate)


def severity_of(category: str) -> str:
    return _SEVERITY.get(category, "low")
