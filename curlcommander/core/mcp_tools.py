"""Pure logic behind the native MCP server (Fase 1).

This module has **no dependency on the MCP SDK**. It exposes plain async/sync
functions that operate on the existing core (``send``, ``build_curl``,
``parse_curl``, ``intruder``, ``passive``, ``payload_catalog``, the history
store) and return JSON-serialisable ``dict`` results. ``mcp_server`` is a thin
FastMCP wrapper that registers these; keeping the logic here means it is fully
unit-testable without installing ``mcp`` — the same split the project uses for
the mitmproxy-backed :mod:`curlcommander.core.proxy`.

A session-wide **scope allowlist** is enforced on every outbound request so an
AI driving the tool through MCP cannot reach a host the operator did not put in
scope. The scope is empty by default, which — matching the CLI — means "no
restriction"; call :func:`set_scope` to lock the AI to an engagement's targets.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from curlcommander.core import passive, scope
from curlcommander.core.curl_builder import build_curl
from curlcommander.core.curl_parser import parse_curl
from curlcommander.core.http_client import send
from curlcommander.core.redaction import redact_config
from curlcommander.core.request_model import HistoryEntry, RequestConfig, ResponseResult
from curlcommander.storage.history_repo import HistoryRepo


class MCPToolError(RuntimeError):
    """A tool call was rejected (bad input or out-of-scope target)."""


@dataclass
class ToolContext:
    """Shared state for a running MCP session: scope, engagement, history."""

    repo: HistoryRepo | None = None
    engagement: str = ""
    scope_entries: list[str] = field(default_factory=list)
    # Safety cap so an AI cannot launch an unbounded Intruder run by accident.
    max_intruder_requests: int = 5000

    def enforce(self, url: str) -> None:
        if self.scope_entries:
            try:
                scope.enforce(url, self.scope_entries)
            except scope.ScopeError as exc:
                raise MCPToolError(str(exc)) from exc


# ---------------------------------------------------------------------------
# RequestConfig construction / serialisation
# ---------------------------------------------------------------------------


def config_from_params(params: dict[str, Any]) -> RequestConfig:
    """Build a :class:`RequestConfig` from a loose JSON dict.

    Accepts either a full ``to_dict`` payload or the ergonomic subset an AI is
    likely to send (``url``, ``method``, ``headers`` as a mapping, ``json``/
    ``body``). Unknown keys are ignored by ``from_dict``.
    """
    data = dict(params)
    if "url" not in data or not data["url"]:
        raise MCPToolError("'url' is required")
    data.setdefault("method", "GET")
    # ``json`` is a convenience alias: a mapping/str body that also sets type.
    if "json" in data and "body" not in data:
        body = data.pop("json")
        import json as _json

        data["body"] = body if isinstance(body, str) else _json.dumps(body)
        data.setdefault("body_type", "json")
    # Headers/params/cookies/form may arrive either as a plain mapping (what an
    # AI naturally emits) or as the list-of-pairs ``to_dict`` format. from_dict
    # only understands the latter, so pull the pair fields out, let from_dict
    # handle the scalars, then assign the pairs via the constructor's coerce
    # (which accepts dict / list-of-pairs / HeaderList alike).
    pair_fields = {"headers", "params", "cookies", "form"}
    pairs = {k: data.pop(k) for k in list(data) if k in pair_fields}
    try:
        config = RequestConfig.from_dict(data)
        # Assign the pair fields raw, then re-run __post_init__ so its coerce()
        # normalises dict / list-of-pairs / HeaderList into HeaderList uniformly.
        for name, value in pairs.items():
            setattr(config, name, value)
        config.__post_init__()
        return config
    except (TypeError, ValueError) as exc:
        raise MCPToolError(f"invalid request parameters: {exc}") from exc


def _response_summary(result: ResponseResult, *, max_body: int = 20000) -> dict[str, Any]:
    body = result.body or ""
    truncated = len(body) > max_body
    return {
        "status_code": result.status_code,
        "reason": result.reason,
        "headers": result.headers,
        "content_type": result.content_type,
        "duration_ms": round(result.duration_ms, 2),
        "size_bytes": result.size_bytes,
        "body": body[:max_body],
        "body_truncated": truncated,
        "error": result.error,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def send_request(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Send one HTTP request and return the response summary plus its curl.

    Respects the session scope allowlist and records the exchange in history.
    """
    config = config_from_params(params)
    ctx.enforce(config.url)
    curl = build_curl(config)
    result = await send(config)
    if ctx.repo is not None:
        try:
            entry = HistoryEntry(
                id=0,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                request=redact_config(config, {}),
                status_code=result.status_code,
                duration_ms=result.duration_ms,
                curl_cmd=curl,
                response_body=result.content,
                response_content_type=result.content_type,
                origin="mcp",
                engagement=ctx.engagement,
            )
            entry_id = ctx.repo.save(entry)
        except Exception:
            entry_id = None
    else:
        entry_id = None
    return {
        "request": {"method": config.method, "url": config.url},
        "curl": curl,
        "response": _response_summary(result),
        "history_id": entry_id,
    }


def gen_curl(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Return the faithful ``curl`` command for a request, without sending it."""
    config = config_from_params(params)
    return {"curl": build_curl(config)}


def import_curl(command: str, ctx: ToolContext) -> dict[str, Any]:
    """Parse a ``curl`` command string into a structured request config."""
    if not command or not command.strip():
        raise MCPToolError("empty curl command")
    try:
        config = parse_curl(command)
    except Exception as exc:  # CurlParseError and friends
        raise MCPToolError(f"could not parse curl: {exc}") from exc
    return {"config": config.to_dict()}


async def passive_scan(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Send a request (if a full config is given) or scan a supplied response.

    When ``params`` contains ``url`` the request is sent first; the passive
    analyzer then runs over the response (security headers, cookies, CORS,
    verbose errors, leaked secrets, fingerprints).
    """
    config = config_from_params(params)
    ctx.enforce(config.url)
    result = await send(config)
    findings = passive.analyze(result, config.url)
    return {
        "url": config.url,
        "status_code": result.status_code,
        "findings": [
            {"severity": f.severity, "category": f.category, "title": f.title, "detail": f.detail} for f in findings
        ],
    }


async def intruder_attack(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Run an Intruder attack.

    ``params``: ``base`` (a request config whose fields carry FUZZ markers),
    ``mode`` (sniper|battering-ram|pitchfork|cluster-bomb), ``wordlists`` (list
    of lists, or ``payloads`` = list of catalog category names), optional
    ``concurrency``/``rate``/``filters``.
    """
    from curlcommander.core import intruder, payload_catalog

    base = config_from_params(params.get("base") or params)
    ctx.enforce(base.url)
    mode = params.get("mode", "sniper")
    if mode not in intruder.ATTACK_MODES:
        raise MCPToolError(f"unknown mode {mode!r} (known: {', '.join(intruder.ATTACK_MODES)})")

    wordlists: list[list[str]] = []
    for wl in params.get("wordlists") or []:
        wordlists.append([str(x) for x in wl])
    for cat in params.get("payloads") or []:
        wordlists.append(payload_catalog.load_category(str(cat)))
    if not wordlists or any(not wl for wl in wordlists):
        raise MCPToolError("provide non-empty 'wordlists' or 'payloads'")

    originals = params.get("originals")
    if mode == "sniper" and not originals:
        raise MCPToolError(
            "sniper mode needs 'originals': the literal value of each marked position "
            "(one per FUZZ1/FUZZ2/... marker). Use battering-ram for a single FUZZ marker."
        )

    total = sum(len(wl) for wl in wordlists) if mode == "sniper" else max(len(wl) for wl in wordlists)
    if total > ctx.max_intruder_requests:
        raise MCPToolError(f"attack would issue ~{total} requests, over the {ctx.max_intruder_requests} cap")

    filt = None
    fspec = params.get("filters")
    if fspec:
        from curlcommander.core.fuzzer import FuzzFilters

        filt = FuzzFilters(
            match_codes=set(fspec["match_codes"]) if fspec.get("match_codes") else None,
            filter_codes=set(fspec["filter_codes"]) if fspec.get("filter_codes") else None,
            match_size=fspec.get("match_size"),
            filter_size=fspec.get("filter_size"),
            match_regex=fspec.get("match_regex"),
        )

    results = await intruder.run_attack(
        base,
        mode,
        wordlists,
        originals=originals,
        filters=filt,
        concurrency=int(params.get("concurrency", 10)),
        rate=float(params.get("rate", 0.0)),
    )
    return {
        "mode": mode,
        "count": len(results),
        "results": [
            {
                "payloads": r.payloads,
                "status_code": r.status_code,
                "size_bytes": r.size_bytes,
                "duration_ms": round(r.duration_ms, 2),
                "matched_regex": r.matched_regex,
                "anomaly": r.anomaly,
                "error": r.error,
            }
            for r in results
        ],
    }


# -- scope & history --------------------------------------------------------


def set_scope(entries: list[str], ctx: ToolContext) -> dict[str, Any]:
    """Replace the session scope allowlist (host globs / CIDRs, ``!`` to deny)."""
    ctx.scope_entries = [str(e).strip() for e in entries if str(e).strip()]
    return {"scope": ctx.scope_entries}


def get_scope(ctx: ToolContext) -> dict[str, Any]:
    return {"scope": ctx.scope_entries, "engagement": ctx.engagement}


def list_payload_categories(ctx: ToolContext) -> dict[str, Any]:
    from curlcommander.core import payload_catalog

    return {"categories": payload_catalog.categories()}


def history_list(ctx: ToolContext, limit: int = 50) -> dict[str, Any]:
    if ctx.repo is None:
        return {"entries": []}
    entries = ctx.repo.load(limit=limit)
    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "method": e.request.method,
                "url": e.request.url,
                "status_code": e.status_code,
                "duration_ms": round(e.duration_ms, 2),
                "origin": e.origin,
            }
            for e in entries
        ]
    }


def history_get(id: int, ctx: ToolContext) -> dict[str, Any]:
    if ctx.repo is None:
        raise MCPToolError("no history store available")
    entry = ctx.repo.get_by_id(id)
    if entry is None:
        raise MCPToolError(f"no history entry with id {id}")
    return {
        "id": entry.id,
        "timestamp": entry.timestamp,
        "config": entry.request.to_dict(),
        "status_code": entry.status_code,
        "curl": entry.curl_cmd,
    }


def _run(coro: Any) -> Any:
    """Run an async tool from a sync context (used only in tests/CLI helpers)."""
    return asyncio.run(coro)
