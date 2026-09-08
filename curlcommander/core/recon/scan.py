"""Per-tool recon workflows: subfinder, httpx, nuclei, katana (item 7).

Each function builds the right argv for its tool (JSON/JSONL output, always
``-silent``) and streams parsed records via ``tools.run_and_stream``. Scope is
enforced *before* anything is sent over the network, matching every other
network-touching feature in this codebase (``core.scope.enforce``):

* ``subfinder``/``katana`` take a single target (a domain / a start URL) —
  refused outright (``ScopeError``) if it is not in scope, the same "hard
  refuse" behaviour as ``validate``/``bounty-scan``/``proxy``.
* ``httpx``/``nuclei`` take a *list* of hosts/URLs to actively probe — each
  one is checked before it ever reaches the tool's input, and out-of-scope
  entries are dropped (not sent) and counted, rather than aborting the whole
  batch over one bad line in a large recon list.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from curlcommander.core import scope
from curlcommander.core.recon.tools import run_and_stream


@dataclass
class ScopedBatch:
    """Result of filtering a batch of hosts/URLs against scope."""

    kept: list[str] = field(default_factory=list)
    dropped: int = 0


def filter_scope(items: list[str], scope_entries: list[str] | None, *, is_url: bool) -> ScopedBatch:
    """Pure filter, exposed so a caller can report how many were dropped
    before the (async) network-touching scan even starts."""
    if not scope_entries:
        return ScopedBatch(kept=list(items), dropped=0)
    check = scope.url_in_scope if is_url else scope.host_in_scope
    kept = [i for i in items if check(i, scope_entries)]
    return ScopedBatch(kept=kept, dropped=len(items) - len(kept))


async def subfinder(domain: str, scope_entries: list[str] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Subdomain enumeration: ``subfinder -d {domain} -json -silent``."""
    if scope_entries:
        scope.enforce(domain, scope_entries)
    async for record in run_and_stream("subfinder", ["-d", domain, "-json", "-silent"]):
        yield record


async def httpx_probe(hosts: list[str], scope_entries: list[str] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Live-host probing: ``httpx -l hosts.txt -json -silent -sc -title -tech-detect``.

    ``hosts`` is filtered against scope *before* it ever reaches httpx — an
    out-of-scope host in the input list is never probed, not merely hidden
    from the output afterward.
    """
    batch = filter_scope(hosts, scope_entries, is_url=False)
    if not batch.kept:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(batch.kept))
        list_path = f.name
    try:
        async for record in run_and_stream(
            "httpx", ["-l", list_path, "-json", "-silent", "-sc", "-title", "-tech-detect"]
        ):
            yield record
    finally:
        Path(list_path).unlink(missing_ok=True)


async def nuclei_scan(
    urls: list[str],
    severities: list[str] | None = None,
    scope_entries: list[str] | None = None,
    include_raw: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Vulnerability templates: ``nuclei -l urls.txt -jsonl -silent -severity ...``.

    ``urls`` is filtered against scope before reaching nuclei, same reasoning
    as :func:`httpx_probe` — nuclei actively sends requests to every URL.
    """
    batch = filter_scope(urls, scope_entries, is_url=True)
    if not batch.kept:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(batch.kept))
        list_path = f.name
    args = ["-l", list_path, "-jsonl", "-silent"]
    if severities:
        args += ["-severity", ",".join(severities)]
    if include_raw:
        args += ["-include-rr"]
    try:
        async for record in run_and_stream("nuclei", args):
            yield record
    finally:
        Path(list_path).unlink(missing_ok=True)


async def katana_crawl(url: str, scope_entries: list[str] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Crawling: ``katana -u {url} -jsonl -silent`` — feeds real endpoints to
    discover/fuzz instead of a blind wordlist."""
    if scope_entries:
        scope.enforce(url, scope_entries)
    async for record in run_and_stream("katana", ["-u", url, "-jsonl", "-silent"]):
        yield record


def katana_url(record: dict[str, Any]) -> str:
    """Best-effort URL extraction from a katana record (nested under ``request``
    in real katana output; top-level ``url`` in the brief's simplified shape)."""
    if "url" in record:
        return str(record["url"])
    request = record.get("request")
    if isinstance(request, dict):
        return str(request.get("endpoint") or request.get("url") or "")
    return ""
