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
    # When the operator started the session with a scope (e.g. `curlcmd mcp
    # --scope`), that scope is an authorization boundary the untrusted MCP
    # caller must not be able to widen or clear: set_scope is refused.
    scope_locked: bool = False
    # Safety cap so an AI cannot launch an unbounded Intruder run by accident.
    max_intruder_requests: int = 5000
    # User plugins, loaded once on first use (None = not yet loaded).
    _plugins: Any = None

    def plugins(self) -> Any:
        """The loaded plugin registry (cached per session)."""
        if self._plugins is None:
            from curlcommander.core import plugins as plugmod

            self._plugins = plugmod.load_plugins()
        return self._plugins

    def enforce(self, url: str) -> None:
        if self.scope_entries:
            try:
                scope.enforce(url, self.scope_entries)
            except scope.ScopeError as exc:
                raise MCPToolError(str(exc)) from exc

    def prepare(self, config: RequestConfig) -> None:
        """Enforce scope on the target and keep the boundary across redirects.

        With ``follow_redirects=True`` httpx would chase a 3xx to any host
        without a second scope check, letting an in-scope endpoint bounce the
        request out of scope (common when probing open redirects). While a
        scope is set, auto-redirect is disabled so each hop must be re-issued
        (and re-checked) explicitly.
        """
        self.enforce(config.url)
        if self.scope_entries:
            config.follow_redirects = False


def _record_send(ctx: ToolContext, config: RequestConfig, result: ResponseResult, origin: str = "mcp") -> int | None:
    """Persist an MCP-issued request/response to history, redaction-safe.

    Both the stored request *and* its curl are built from the redacted config,
    so a credential (Authorization/cookie/API key) never lands in the history
    database or comes back out through ``history_get``.
    """
    if ctx.repo is None:
        return None
    try:
        redacted = redact_config(config, {})
        entry = HistoryEntry(
            id=0,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            request=redacted,
            status_code=result.status_code,
            duration_ms=result.duration_ms,
            curl_cmd=build_curl(redacted),
            response_body=result.content,
            response_content_type=result.content_type,
            origin=origin,
            engagement=ctx.engagement,
        )
        return ctx.repo.save(entry)
    except Exception:
        return None


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
    ctx.prepare(config)
    curl = build_curl(config)
    result = await send(config)
    entry_id = _record_send(ctx, config, result)
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
    ctx.prepare(config)
    result = await send(config)
    _record_send(ctx, config, result, origin="mcp-scan")
    findings = passive.analyze(result, config.url)
    from curlcommander.core import plugins as plugmod

    findings += plugmod.run_passive_plugins(ctx.plugins(), result, config.url)
    return {
        "url": config.url,
        "status_code": result.status_code,
        "findings": [
            {"severity": f.severity, "category": f.category, "title": f.title, "detail": f.detail} for f in findings
        ],
    }


async def active_scan(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Run the active scanner: inject payloads into each parameter and report.

    Covers reflected XSS, error-based SQLi, SSTI, path traversal and open
    redirect. Scope-enforced; a scoped session keeps redirects manual.
    """
    from curlcommander.core import active

    config = config_from_params(params)
    ctx.enforce(config.url)
    if ctx.scope_entries:
        config.follow_redirects = False

    # Route the scanner's sends through the scope check + history, so every
    # crafted request is confined and audited like a normal MCP send.
    async def _sender(cfg: RequestConfig) -> ResponseResult:
        ctx.enforce(cfg.url)
        result = await send(cfg)
        _record_send(ctx, cfg, result, origin="mcp-active")
        return result

    findings = await active.active_scan(config, sender=_sender)
    from curlcommander.core import plugins as plugmod

    findings += await plugmod.run_active_plugins(ctx.plugins(), config, _sender)
    return {
        "url": config.url,
        "findings": [
            {"severity": f.severity, "category": f.category, "title": f.title, "detail": f.detail} for f in findings
        ],
    }


def estimate_intruder_requests(mode: str, wordlists: list[list[str]], originals: list[str] | None) -> int:
    """Upper bound on the requests an attack will issue, per mode.

    Critically, ``cluster-bomb`` fires the **Cartesian product** of every
    wordlist, so the estimate must multiply the lengths — using only the
    largest list (three 100-item lists reading as 100 instead of 1,000,000)
    would let the cap be blown past by orders of magnitude.
    """
    import math

    lengths = [len(wl) for wl in wordlists]
    if not lengths:
        return 0
    if mode == "cluster-bomb":
        return math.prod(lengths)
    if mode == "sniper":
        # One wordlist, replayed once per marked position.
        return lengths[0] * max(1, len(originals or []))
    # battering-ram: one list fills every position at once; pitchfork: lists
    # advance in lockstep (min length) — max is a safe over-estimate for both.
    return max(lengths)


async def intruder_attack(params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Run an Intruder attack.

    ``params``: ``base`` (a request config whose fields carry FUZZ markers),
    ``mode`` (sniper|battering-ram|pitchfork|cluster-bomb), ``wordlists`` (list
    of lists, or ``payloads`` = list of catalog category names), optional
    ``concurrency``/``rate``/``filters``.
    """
    from curlcommander.core import intruder, payload_catalog

    base = config_from_params(params.get("base") or params)
    ctx.prepare(base)
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

    total = estimate_intruder_requests(mode, wordlists, originals)
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
    # Audit trail: record that an AI-driven attack ran (mode, size, anomalies)
    # against the base target, so the engagement history reflects the action.
    if ctx.repo is not None:
        try:
            anomalies = sum(1 for r in results if r.anomaly)
            redacted = redact_config(base, {})
            ctx.repo.save(
                HistoryEntry(
                    id=0,
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    request=redacted,
                    status_code=None,
                    duration_ms=0.0,
                    curl_cmd=f"# intruder {mode}: {len(results)} request(s), {anomalies} anomaly(ies)",
                    origin="mcp-intruder",
                    engagement=ctx.engagement,
                )
            )
        except Exception:
            pass
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
    """Replace the session scope allowlist (host globs / CIDRs, ``!`` to deny).

    Refused when the operator locked the scope at startup (``curlcmd mcp
    --scope``): an untrusted MCP caller must not be able to widen or clear the
    authorization boundary it is confined to.
    """
    if ctx.scope_locked:
        raise MCPToolError(
            "scope is locked by the operator (started with --scope) and cannot be changed from this session"
        )
    ctx.scope_entries = [str(e).strip() for e in entries if str(e).strip()]
    return {"scope": ctx.scope_entries}


def get_scope(ctx: ToolContext) -> dict[str, Any]:
    return {"scope": ctx.scope_entries, "engagement": ctx.engagement}


def list_payload_categories(ctx: ToolContext) -> dict[str, Any]:
    from curlcommander.core import payload_catalog

    return {"categories": payload_catalog.categories()}


def list_plugins(ctx: ToolContext) -> dict[str, Any]:
    from curlcommander.core import plugins as plugmod

    return plugmod.summary(ctx.plugins())


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
