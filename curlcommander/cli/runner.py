import asyncio
import os
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from curlcommander.config import DB_PATH, DISPLAY_LIMIT_BYTES
from curlcommander.core import payload_catalog, payload_sources, scope
from curlcommander.core.api_styles import (
    graphql_config,
    graphql_field_names,
    grpc_web_content_type,
    introspection_config,
    introspection_enabled,
    soap_config,
    xml_config,
)
from curlcommander.core.assertions import AssertionSpec, format_report, run_assertions
from curlcommander.core.curl_builder import build_curl
from curlcommander.core.curl_parser import CurlParseError, parse_curl
from curlcommander.core.discovery import (
    BountyReport,
    Candidate,
    category_fuzz,
    discover,
    severity_of,
)
from curlcommander.core.evidence import compose_raw_response, save_evidence
from curlcommander.core.fuzzer import FuzzFilters, find_markers, markers_for, run_fuzz
from curlcommander.core.headers import HeaderList
from curlcommander.core.http_client import send, stream_send
from curlcommander.core.logging_setup import get_logger, setup_logging
from curlcommander.core.parsing import ParseError, parse_headers, parse_params
from curlcommander.core.raw_http import RawRequestError, parse_raw_request_bytes
from curlcommander.core.raw_transport import (
    RawTransportError,
    fix_content_length,
    is_smuggling_shaped,
    send_raw_request,
    serialize_request,
    target_from_url,
)
from curlcommander.core.redaction import has_redacted, redact_config, reveal_config, reveal_text
from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.core.response_formatter import format_body, get_lexer
from curlcommander.storage.history_repo import HistoryRepo

_console = Console()

# Exit codes (curl-compatible where it matters).
EXIT_OK = 0
EXIT_USAGE = 1  # usage / parse / not-found
EXIT_NETWORK = 2  # network / DNS / TLS / timeout
EXIT_ASSERT = 3  # one or more --assert-* checks failed
EXIT_HTTP = 22  # --fail and HTTP status >= 400 (matches curl --fail)


def run_cli(args) -> int:
    setup_logging(getattr(args, "log_file", None), getattr(args, "log_level", None))
    repo = HistoryRepo(DB_PATH)
    try:
        reveal = getattr(args, "reveal", False)
        match args.subcommand:
            case "history":
                return _show_history(repo, reveal=reveal)
            case "replay":
                return _replay(repo, args.id)
            case "curl":
                return _show_curl_from_history(repo, args.id, reveal=reveal)
            case "export-history":
                return _export_history(repo, args.output, reveal=reveal)
            case "delete-history":
                return _delete_history(repo, args.id)
            case "clear-history":
                repo.clear()
                _console.print("[green]History cleared.[/green]")
                return EXIT_OK
            case "payloads":
                return _run_payloads(args)
            case "discover":
                return _run_discover(args)
            case "bounty-scan":
                return _run_bounty_scan(args)
            case "validate":
                return _run_validate(args)
            case _:
                return _run_request(args, repo)
    except scope.ScopeError as exc:
        _console.print(f"[red bold]Refused:[/red bold] {exc}")
        return EXIT_USAGE
    except RawTransportError as exc:
        _console.print(f"[red bold]Error:[/red bold] {exc}")
        return EXIT_NETWORK
    except (ParseError, CurlParseError, RawRequestError, FileNotFoundError) as exc:
        _console.print(f"[red bold]Error:[/red bold] {exc}")
        return EXIT_USAGE
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _show_history(repo: HistoryRepo, reveal: bool = False) -> int:
    entries = repo.load()
    if not entries:
        _console.print("[dim]No history entries.[/dim]")
        return EXIT_OK

    env = dict(os.environ)

    table = Table(title="Request History", show_lines=False)
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Timestamp")
    table.add_column("Method")
    table.add_column("URL", no_wrap=True, max_width=50)
    table.add_column("Status", justify="center")
    table.add_column("ms", justify="right")

    for entry in entries:
        style = _status_style(entry.status_code)
        url = reveal_text(entry.request.url, env) if reveal else entry.request.url
        table.add_row(
            str(entry.id),
            entry.timestamp,
            entry.request.method,
            url,
            f"[{style}]{entry.status_code or 'ERR'}[/{style}]",
            f"{entry.duration_ms:.0f}",
        )

    _console.print(table)
    return EXIT_OK


def _replay(repo: HistoryRepo, id: int) -> int:
    entry = repo.get_by_id(id)
    if entry is None:
        _console.print(f"[red]No history entry with ID {id}.[/red]")
        return EXIT_USAGE

    # Stored requests are redacted; resolve {{VAR}} references from the
    # environment and refuse to send an unrecoverable REDACTED credential (1.4).
    prepared = reveal_config(entry.request, dict(os.environ))
    if has_redacted(prepared):
        _console.print(
            "[red]Cannot replay: a credential was redacted at save time.[/red] "
            "Re-run with the original --env-file/env vars set, or the request "
            "was saved with a literal secret that is no longer stored."
        )
        return EXIT_USAGE

    _console.print(f"[dim]Replaying #{id}…[/dim]")
    return _execute_request(prepared, repo)


def _show_curl_from_history(repo: HistoryRepo, id: int, reveal: bool = False) -> int:
    entry = repo.get_by_id(id)
    if entry is None:
        _console.print(f"[red]No history entry with ID {id}.[/red]")
        return EXIT_USAGE

    curl_cmd = reveal_text(entry.curl_cmd, dict(os.environ)) if reveal else entry.curl_cmd
    _print_curl(curl_cmd)
    return EXIT_OK


def _export_history(repo: HistoryRepo, output: str, reveal: bool = False) -> int:
    repo.export_json(output, reveal=reveal)
    _console.print(f"[green]History exported to[/green] [bold]{output}[/bold]")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Request execution
# ---------------------------------------------------------------------------


def _run_request(args, repo: HistoryRepo) -> int:
    no_redact = getattr(args, "no_redact", False)
    if no_redact:
        _console.print(
            "[yellow]warning: --no-redact stores credentials in clear text in the history DB[/yellow]",
        )
    # Raw byte-level path (2B.2): a raw request file, sent over a socket as-is.
    if getattr(args, "raw_request", None):
        return _execute_raw_request(args, repo)

    env_vars: dict[str, str] = {}
    imported = _maybe_import(args)
    if imported is not None:
        config = imported
    elif not args.url:
        from curlcommander.cli.wizard import run_wizard

        config = run_wizard()
        if config is None:
            return EXIT_OK
    else:
        env_vars = _load_env_file(args.env_file) if args.env_file else {}
        config = _build_config(args, env_vars)

    # API styles (2B.6): reshape the config for GraphQL / SOAP / XML / gRPC-web.
    config = _apply_api_style(config, args)

    # --burp shortcut (2B.7): route through Burp/ZAP and skip TLS verify.
    if getattr(args, "burp", False):
        if not config.proxy:
            config.proxy = "http://127.0.0.1:8080"
        config.verify_ssl = False
        _console.print("[yellow]routing through Burp (127.0.0.1:8080), TLS verification off[/yellow]")

    # Scope allowlist enforcement (2B.8): refuse out-of-scope targets.
    if getattr(args, "scope", None):
        scope.enforce(config.url, scope.load_scope(args.scope))

    # Dry run (2B.8): show the wire bytes without sending.
    if getattr(args, "dry_run", False):
        raw = serialize_request(config, no_default_headers=config.no_default_headers)
        _console.print("[dim]--- would send (dry-run) ---[/dim]")
        _console.print(raw.decode("latin-1", errors="replace"), highlight=False)
        _print_curl(build_curl(config))
        return EXIT_OK

    if getattr(args, "graphql_introspection", False):
        return _run_introspection(config)

    if getattr(args, "stream", False):
        return _run_stream(config)

    # Fuzzing (2B.3): a wordlist / built-in payload set plus FUZZ markers.
    if getattr(args, "wordlists", None) or getattr(args, "payloads", None) or getattr(args, "payloads_all", None):
        return _run_fuzz(config, args)

    if args.curl_only:
        curl_cmd = build_curl(config)
        _print_curl(curl_cmd)
        if args.save:
            _persist(config, None, 0.0, repo, env_vars=env_vars, no_redact=no_redact)
        return EXIT_OK

    return _execute_request(
        config,
        repo,
        fail=getattr(args, "fail", False),
        env_vars=env_vars,
        no_redact=no_redact,
        assert_spec=_build_assert_spec(args),
        report_fmt=getattr(args, "report", None),
        evidence_dir=getattr(args, "evidence", None),
        engagement=getattr(args, "engagement", None),
    )


def _read_body_arg(value: str) -> str:
    if value.startswith("@"):
        return Path(value[1:]).read_text(encoding="utf-8")
    return value


def _apply_api_style(config: RequestConfig, args) -> RequestConfig:
    if getattr(args, "graphql", None):
        return graphql_config(config.url, args.graphql, getattr(args, "graphql_vars", None), config.headers)
    if getattr(args, "graphql_introspection", False):
        return introspection_config(config.url, config.headers)
    if getattr(args, "soap", None):
        return soap_config(
            config.url,
            _read_body_arg(args.soap),
            action=getattr(args, "soap_action", None),
            wrap_envelope=getattr(args, "soap_envelope", False),
            headers=config.headers,
        )
    if getattr(args, "xml", None):
        return xml_config(config.url, _read_body_arg(args.xml), headers=config.headers)
    if getattr(args, "grpc_web", False):
        config.headers.setdefault("Content-Type", grpc_web_content_type())
    return config


def _run_introspection(config: RequestConfig) -> int:
    _console.print(f"[dim]→ GraphQL introspection {config.url}[/dim]")
    result = asyncio.run(send(config))
    if result.error:
        _console.print(f"[red bold]Error:[/red bold] {result.error}")
        return EXIT_NETWORK
    if introspection_enabled(result.body):
        names = graphql_field_names(result.body)
        _console.print(f"[red bold]Introspection ENABLED[/red bold] — {len(names)} types exposed")
        _console.print("[dim]" + ", ".join(n for n in names if not n.startswith("__"))[:2000] + "[/dim]")
    else:
        _console.print("[green]Introspection appears disabled.[/green]")
    return EXIT_OK


def _run_stream(config: RequestConfig) -> int:
    _console.print(f"[dim]→ streaming {config.method} {config.url}[/dim]")

    def on_line(line: str) -> None:
        _console.print(line, highlight=False)

    result = asyncio.run(stream_send(config, on_line))
    if result.error:
        _console.print(f"[red bold]Error:[/red bold] {result.error}")
        return EXIT_NETWORK
    _console.print(f"[dim]{result.size_bytes} lines, {result.duration_ms:.0f} ms[/dim]")
    return EXIT_OK


def _resolve_fuzz_wordlists(args) -> list[list[str]]:
    """Resolve -w specs and --payloads/--payloads-all categories via the catalog."""
    wordlists: list[list[str]] = []
    for spec in getattr(args, "wordlists", []) or []:
        wordlists.append(payload_catalog.resolve_spec(spec))
    for cat in getattr(args, "payloads", []) or []:
        wordlists.append(payload_catalog.load_category(cat, all_sources=False))
    for cat in getattr(args, "payloads_all", []) or []:
        wordlists.append(payload_catalog.load_category(cat, all_sources=True))
    return wordlists


def _run_fuzz(config: RequestConfig, args) -> int:
    try:
        wordlists = _resolve_fuzz_wordlists(args)
    except payload_catalog.CatalogError as exc:
        _console.print(f"[red]Error:[/red] {exc}")
        return EXIT_USAGE
    if not wordlists or any(not wl for wl in wordlists):
        _console.print("[red]Error:[/red] a wordlist/payload set is empty or unreadable.")
        return EXIT_USAGE

    markers = markers_for(len(wordlists))
    present = find_markers(config, markers)
    if not present:
        _console.print(
            f"[red]Error:[/red] no fuzz markers found. Place {', '.join(markers)} "
            "in the URL, a header/param/cookie value, or the body."
        )
        return EXIT_USAGE

    filters = FuzzFilters(
        match_codes=_int_set(getattr(args, "mc", None)),
        filter_codes=_int_set(getattr(args, "fc", None)),
        match_size=getattr(args, "ms", None),
        filter_size=getattr(args, "fs", None),
        match_regex=getattr(args, "mr", None),
    )
    encoders = [e for e in (getattr(args, "encode", None) or "").split(",") if e] or None

    results = asyncio.run(
        run_fuzz(
            config,
            wordlists,
            mode=getattr(args, "fuzz_mode", "clusterbomb"),
            filters=filters,
            concurrency=getattr(args, "concurrency", 10),
            rate=getattr(args, "rate", 0.0),
            encoders=encoders,
        )
    )

    table = Table(title=f"Fuzz results ({len(results)} shown)")
    table.add_column("Payload", overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Size", justify="right")
    table.add_column("ms", justify="right")
    table.add_column("", justify="center")
    for r in results:
        style = _status_style(r.status_code)
        table.add_row(
            " / ".join(r.payloads),
            f"[{style}]{r.status_code or 'ERR'}[/{style}]",
            str(r.size_bytes),
            f"{r.duration_ms:.0f}",
            "[bold yellow]★[/bold yellow]" if r.anomaly else "",
        )
    _console.print(table)
    return EXIT_OK


def _run_payloads(args) -> int:
    """`curlcmd payloads sync|update|list|search|show` (G.1-G.3)."""
    cmd = getattr(args, "payloads_cmd", None)
    if cmd == "sync":
        name = getattr(args, "source", None)
        try:
            names = [name] if name else list(payload_sources.load_sources())
            for n in names:
                dest = payload_sources.sync(n)
                _console.print(f"[green]synced[/green] {n} → {dest}")
        except payload_sources.PayloadSourceError as exc:
            _console.print(f"[red]Error:[/red] {exc}")
            return EXIT_USAGE
        return EXIT_OK
    if cmd == "update":
        try:
            for dest in payload_sources.update():
                _console.print(f"[green]updated[/green] {dest}")
        except payload_sources.PayloadSourceError as exc:
            _console.print(f"[red]Error:[/red] {exc}")
            return EXIT_USAGE
        return EXIT_OK
    if cmd == "list":
        category = getattr(args, "category", None)
        if category:
            try:
                files = payload_catalog.category_files(category, all_sources=True)
            except payload_catalog.CatalogError as exc:
                _console.print(f"[red]Error:[/red] {exc}")
                return EXIT_USAGE
            for f in files:
                _console.print(str(f))
        else:
            _console.print("[bold]Categories:[/bold] " + ", ".join(payload_catalog.categories()))
            avail = [n for n in payload_sources.load_sources() if payload_sources.is_available(n)]
            _console.print(
                "[bold]Synced sources:[/bold] " + (", ".join(avail) or "(none — run: curlcmd payloads sync)")
            )
        return EXIT_OK
    if cmd == "search":
        hits = payload_catalog.search(args.term)
        for h in hits:
            _console.print(h)
        if not hits:
            _console.print("[dim]no matches[/dim]")
        return EXIT_OK
    if cmd == "show":
        try:
            lines = payload_catalog.load_category(args.category, all_sources=getattr(args, "all_sources", False))
        except payload_catalog.CatalogError as exc:
            _console.print(f"[red]Error:[/red] {exc}")
            return EXIT_USAGE
        if getattr(args, "count", False):
            _console.print(str(len(lines)))
        else:
            for line in lines[: args.limit]:
                _console.print(line, highlight=False)
            if len(lines) > args.limit:
                _console.print(f"[dim]… {len(lines) - args.limit} more (total {len(lines)})[/dim]")
        return EXIT_OK
    _console.print("[red]Error:[/red] unknown payloads subcommand")
    return EXIT_USAGE


def _discover_filters(args) -> FuzzFilters:
    return FuzzFilters(
        match_codes=_int_set(getattr(args, "mc", None)),
        filter_codes=_int_set(getattr(args, "fc", None)) or {404},
        match_size=getattr(args, "ms", None),
        filter_size=getattr(args, "fs", None),
        match_regex=getattr(args, "mr", None),
    )


def _print_fuzz_table(results, title: str) -> None:
    table = Table(title=title)
    table.add_column("Path/Payload", overflow="fold")
    table.add_column("Status", justify="center")
    table.add_column("Size", justify="right")
    table.add_column("ms", justify="right")
    table.add_column("", justify="center")
    for r in results:
        style = _status_style(r.status_code)
        table.add_row(
            " / ".join(r.payloads),
            f"[{style}]{r.status_code or 'ERR'}[/{style}]",
            str(r.size_bytes),
            f"{r.duration_ms:.0f}",
            "[bold yellow]★[/bold yellow]" if r.anomaly else "",
        )
    _console.print(table)


def _run_discover(args) -> int:
    if getattr(args, "scope", None):
        scope.enforce(args.url, scope.load_scope(args.scope))
    try:
        words: list[str] = []
        for spec in getattr(args, "wordlists", []) or []:
            words += payload_catalog.resolve_spec(spec)
        for cat in getattr(args, "payloads", []) or []:
            words += payload_catalog.load_category(cat)
    except payload_catalog.CatalogError as exc:
        _console.print(f"[red]Error:[/red] {exc}")
        return EXIT_USAGE
    if not words:
        _console.print("[red]Error:[/red] provide -w SPEC or --payloads CAT for discovery.")
        return EXIT_USAGE

    exts = [e for e in (getattr(args, "extensions", None) or "").split(",") if e] or None
    results = asyncio.run(
        discover(
            args.url,
            words,
            extensions=exts,
            filters=_discover_filters(args),
            concurrency=getattr(args, "concurrency", 20),
            rate=getattr(args, "rate", 0.0),
            recurse=getattr(args, "recurse", 0),
            verify_ssl=not getattr(args, "no_verify", False),
            timeout=getattr(args, "timeout", 30.0),
        )
    )
    _print_fuzz_table(results, f"Discovery — {len(results)} hits")
    return EXIT_OK


def _run_validate(args) -> int:
    """`curlcmd validate <kind> <url>` — HTTP or browser-executed validators."""
    kind = args.kind
    scope_entries = scope.load_scope(args.scope) if getattr(args, "scope", None) else []
    if scope_entries:
        scope.enforce(args.url, scope_entries)
    if not getattr(args, "engagement", None):
        _console.print("[red]Refused:[/red] validate requires --engagement LABEL (authorization).")
        return EXIT_USAGE

    verify = not getattr(args, "no_verify", False)
    timeout = getattr(args, "timeout", 30.0)
    evidence_dir = getattr(args, "evidence", None)
    shot = str(Path(evidence_dir) / f"{kind}.png") if evidence_dir else None
    if evidence_dir:
        Path(evidence_dir).mkdir(parents=True, exist_ok=True)

    from curlcommander.core import browser

    try:
        if kind == "cors":
            from curlcommander.core.validators.cors import validate_cors

            result = asyncio.run(validate_cors(args.url, origin=args.origin, verify_ssl=verify, timeout=timeout))
        elif kind == "open-redirect":
            from curlcommander.core.validators.redirect import validate_open_redirect

            result = asyncio.run(validate_open_redirect(args.url, verify_ssl=verify, timeout=timeout))
        else:
            browser.require_browser()
            result = asyncio.run(_run_browser_validator(kind, args, scope_entries, shot))
    except browser.BrowserError as exc:
        _console.print(f"[yellow]{exc}[/yellow]")
        return EXIT_USAGE

    colour = {"CONFIRMED": "red", "REFLECTED": "yellow", "NOT_VULNERABLE": "green", "ERROR": "red"}.get(
        result.verdict, "white"
    )
    _console.print(f"[{colour} bold]{result.verdict}[/{colour} bold] {kind}: {result.detail} [dim]({result.url})[/dim]")
    if result.payload:
        _console.print(f"[dim]payload:[/dim] {result.payload}")
    if shot and result.evidence.get("screenshot"):
        _console.print(f"[green]screenshot →[/green] {shot}")
    return EXIT_OK if result.verdict != "ERROR" else EXIT_NETWORK


async def _run_browser_validator(kind: str, args, scope_entries, shot):
    from curlcommander.core.browser import BrowserSession

    async with BrowserSession(
        headless=not getattr(args, "headed", False),
        scope_entries=scope_entries,
        timeout_ms=int(getattr(args, "timeout", 30.0) * 1000),
    ) as session:
        if kind == "xss":
            from curlcommander.core.validators.xss import validate_xss

            return await validate_xss(session, args.url, screenshot_path=shot)
        if kind == "clickjacking":
            from curlcommander.core.validators.clickjacking import validate_clickjacking

            return await validate_clickjacking(session, args.url, screenshot_path=shot)
        if kind == "csrf":
            from curlcommander.core.validators.csrf import validate_csrf

            return await validate_csrf(session, args.url, screenshot_path=shot)
        raise ValueError(f"unknown validator: {kind}")


def _run_bounty_scan(args) -> int:
    if getattr(args, "scope", None):
        scope.enforce(args.url, scope.load_scope(args.scope))
    if not getattr(args, "engagement", None):
        _console.print("[red]Refused:[/red] bounty-scan requires --engagement LABEL (authorization).")
        return EXIT_USAGE

    report = BountyReport(url=args.url)
    categories = [c.strip() for c in (args.categories or "").split(",") if c.strip()]
    param_url = args.url + ("&" if "?" in args.url else "?") + "fuzzcc=FUZZ"

    for cat in categories:
        try:
            payloads_list = payload_catalog.load_category(cat, all_sources=True)
        except payload_catalog.CatalogError:
            continue
        if not payloads_list:
            continue
        results = asyncio.run(
            category_fuzz(
                param_url,
                cat,
                payloads_list,
                concurrency=getattr(args, "concurrency", 10),
                rate=getattr(args, "rate", 0.0),
                verify_ssl=not getattr(args, "no_verify", False),
                timeout=getattr(args, "timeout", 30.0),
            )
        )
        for r in results:
            if r.anomaly:
                report.candidates.append(
                    Candidate(
                        cat,
                        severity_of(cat),
                        r.payloads[-1],
                        r.status_code,
                        r.size_bytes,
                        note="anomalous response vs baseline",
                    )
                )

    buckets = report.by_severity()
    total = sum(len(v) for v in buckets.values())
    _console.print(
        f"[bold]bounty-scan[/bold] {args.url} — {total} candidate(s) [dim](engagement {args.engagement})[/dim]"
    )
    for sev in ("high", "medium", "low"):
        for c in buckets.get(sev, []):
            colour = {"high": "red", "medium": "yellow", "low": "cyan"}[sev]
            _console.print(
                f"[{colour}]{sev.upper()}[/{colour}] {c.category}: {c.payload!r} → {c.status_code} ({c.size_bytes} B)"
            )
    if total == 0:
        _console.print("[dim]No anomalies flagged. Candidates are leads to investigate, not confirmations.[/dim]")
    return EXIT_OK


def _int_set(value: str | None) -> set[int] | None:
    if not value:
        return None
    out: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out or None


def _execute_raw_request(args, repo: HistoryRepo) -> int:
    """Send a raw HTTP request block byte-for-byte over a socket (2B.2)."""
    # Binary read: no universal-newline translation (Windows would collapse
    # \r\n and destroy chunked/CL.TE framing). F1.1
    raw = Path(args.raw_request).read_bytes()

    # Convenience: recompute a lone Content-Length to match the body, but only
    # when the request is not a deliberate smuggling payload, and never with
    # --no-fix-length. Smuggling/chunked requests are sent exactly as written.
    if not getattr(args, "no_fix_length", False) and not is_smuggling_shaped(raw):
        raw = fix_content_length(raw)

    host_arg = getattr(args, "host", None)
    if host_arg:
        host, port, use_tls = target_from_url(host_arg)
    else:
        host, port, use_tls = _target_from_raw(raw)

    if getattr(args, "scope", None):
        scope.enforce(host, scope.load_scope(args.scope))

    verify = not getattr(args, "no_verify", False)
    timeout = getattr(args, "timeout", 30.0)

    _console.print("[dim]--- raw request ---[/dim]")
    _console.print(raw.decode("latin-1", errors="replace"), highlight=False)

    if getattr(args, "dry_run", False):
        _console.print("[dim](dry-run: not sent)[/dim]")
        return EXIT_OK

    result = send_raw_request(raw, host, port, use_tls, verify, timeout)
    if result.error:
        _console.print(f"[red bold]Error:[/red bold] {result.error}")
        return EXIT_NETWORK

    _console.print("[dim]--- raw response ---[/dim]")
    _console.print(result.content.decode("latin-1", errors="replace"), highlight=False)

    # Persist a best-effort config view for history.
    try:
        cfg = parse_raw_request_bytes(raw, host=host_arg)
        _persist(cfg, result.status_code, result.duration_ms, repo)
    except (RawRequestError, ValueError):
        pass
    return EXIT_OK


def _target_from_raw(raw: bytes) -> tuple[str, int, bool]:
    for line in raw.split(b"\r\n")[1:]:
        if line.lower().startswith(b"host:"):
            return target_from_url(line.split(b":", 1)[1].strip().decode("latin-1"))
    raise RawTransportError("no --host and no Host header; cannot route raw request")


def _build_assert_spec(args) -> AssertionSpec:
    return AssertionSpec(
        status=getattr(args, "assert_status", None),
        headers=getattr(args, "assert_headers", None) or None,
        body_contains=getattr(args, "assert_body", None) or None,
        jsonpaths=getattr(args, "assert_jsonpath", None) or None,
        max_ms=getattr(args, "assert_max_ms", None),
    )


def _report_assertions(result, spec: AssertionSpec, report_fmt: str | None, url: str) -> bool:
    """Print assertion outcomes; return True if all passed."""
    results = run_assertions(result, spec)
    if report_fmt:
        print(format_report(results, report_fmt, url=url))
    else:
        for r in results:
            mark = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
            _console.print(f"{mark} {r.name}" + (f"  [dim]({r.detail})[/dim]" if r.detail else ""))
    return all(r.passed for r in results)


def _execute_request(
    config: RequestConfig,
    repo: HistoryRepo,
    fail: bool = False,
    env_vars: dict[str, str] | None = None,
    no_redact: bool = False,
    assert_spec: AssertionSpec | None = None,
    report_fmt: str | None = None,
    evidence_dir: str | None = None,
    engagement: str | None = None,
) -> int:
    if not config.verify_ssl:
        _console.print("[yellow]warning: TLS verification disabled (--no-verify)[/yellow]")

    get_logger().info("request %s %s", config.method, config.url)
    _console.print(f"[dim]→ {config.method} {config.url}[/dim]")

    if config.raw_path:
        # Byte-faithful request line via the raw socket transport (2B.1).
        host, port, use_tls = target_from_url(config.url)
        raw = serialize_request(config, no_default_headers=config.no_default_headers)
        _console.print("[dim]--- raw request ---[/dim]")
        _console.print(raw.decode("latin-1", errors="replace"), highlight=False)
        result = send_raw_request(raw, host, port, use_tls, config.verify_ssl, config.timeout)
    else:
        result = asyncio.run(send(config))

    if result.error:
        get_logger().error("network error for %s: %s", config.url, result.error)
        _console.print(f"[red bold]Error:[/red bold] {result.error}")
        _persist(config, None, result.duration_ms, repo, env_vars=env_vars, no_redact=no_redact)
        return EXIT_NETWORK

    get_logger().info("response %s %s in %.0fms", result.status_code, config.url, result.duration_ms)

    style = _status_style(result.status_code)
    status_line = Text()
    status_line.append(f"{result.status_code} {result.reason}", style=f"bold {style}")
    status_line.append(f"  {result.duration_ms:.0f} ms  {result.size_bytes} B", style="dim")
    _console.print(status_line)

    header_table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 1))
    header_table.add_column("Header", style="cyan")
    header_table.add_column("Value")
    for k, v in result.headers.items():
        header_table.add_row(k, v)
    _console.print(header_table)

    # Save the full raw bytes first, independent of what we render (1.8).
    if config.output_path:
        Path(config.output_path).write_bytes(result.content)
        _console.print(f"[green]Response body saved to[/green] [bold]{config.output_path}[/bold]")

    if result.body:
        # JSON is pretty-printed automatically; --raw turns all formatting off (1.10).
        body_text = result.body if config.raw else format_body(result.body, result.content_type)

        # Truncate what we render so a huge payload can't freeze the terminal (1.9).
        truncated = False
        if len(body_text) > DISPLAY_LIMIT_BYTES:
            body_text = body_text[:DISPLAY_LIMIT_BYTES]
            truncated = True

        _console.print(Syntax(body_text, get_lexer(result.content_type), theme="monokai", word_wrap=True))
        if truncated:
            hint = (
                f" — full body saved to {config.output_path}"
                if config.output_path
                else " — use --output to save the full body"
            )
            _console.print(
                f"[yellow]… output truncated at {DISPLAY_LIMIT_BYTES} bytes"
                f" ({result.size_bytes} B total){hint}[/yellow]"
            )

    _persist(config, result.status_code, result.duration_ms, repo, env_vars=env_vars, no_redact=no_redact)

    if evidence_dir:
        raw_req = serialize_request(config, no_default_headers=config.no_default_headers)
        folder = save_evidence(
            evidence_dir,
            config,
            raw_req,
            compose_raw_response(result),
            result,
            engagement=engagement,
        )
        _console.print(f"[green]Evidence saved to[/green] [bold]{folder}[/bold]")

    if assert_spec is not None and not assert_spec.is_empty():
        if not _report_assertions(result, assert_spec, report_fmt, config.url):
            return EXIT_ASSERT

    if fail and result.status_code is not None and result.status_code >= 400:
        return EXIT_HTTP
    return EXIT_OK


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _maybe_import(args) -> RequestConfig | None:
    """Build a config from a --import* source, or None if none was given."""
    if getattr(args, "import_curl", None):
        return parse_curl(args.import_curl)
    if getattr(args, "import_file", None):
        return parse_curl(Path(args.import_file).read_text(encoding="utf-8"))
    if getattr(args, "import_clipboard", False):
        from curlcommander.core.clipboard import read_clipboard

        return parse_curl(read_clipboard())
    if getattr(args, "import_raw", None):
        data = Path(args.import_raw).read_bytes()  # byte-faithful (F1.1)
        return parse_raw_request_bytes(data, host=getattr(args, "host", None))
    return None


def _build_config(args, env_vars: dict[str, str] | None = None) -> RequestConfig:
    env_vars = env_vars if env_vars is not None else (_load_env_file(args.env_file) if args.env_file else {})
    headers = parse_headers(args.headers)
    params = parse_params(args.params)

    body = ""
    body_type = "none"

    if args.json_body:
        body, body_type = args.json_body, "json"
    elif args.form_body:
        body, body_type = args.form_body, "form"
    elif args.body_file:
        body, body_type = Path(args.body_file).read_text(encoding="utf-8"), "raw"
    elif args.body:
        body, body_type = args.body, "raw"

    auth_type, auth_value = "none", ""
    if args.auth_bearer:
        auth_type, auth_value = "bearer", args.auth_bearer
    elif args.auth_basic:
        auth_type, auth_value = "basic", args.auth_basic
    elif args.auth_apikey:
        auth_type, auth_value = "apikey", args.auth_apikey

    cookies = HeaderList()
    for c in getattr(args, "cookies", []) or []:
        k, _, v = c.partition("=")
        cookies.append(k.strip(), v)

    form = HeaderList()
    for f in getattr(args, "form", []) or []:
        name, _, spec = f.partition("=")
        form.append(name.strip(), spec)

    url = _substitute_variables(args.url or "", env_vars)
    headers = HeaderList([(k, _substitute_variables(v, env_vars)) for k, v in headers])
    params = HeaderList([(k, _substitute_variables(v, env_vars)) for k, v in params])
    body = _substitute_variables(body, env_vars)
    auth_value = _substitute_variables(auth_value, env_vars)

    return RequestConfig(
        method=args.method.upper(),
        url=url,
        headers=headers,
        params=params,
        cookies=cookies,
        form=form,
        no_default_headers=getattr(args, "no_default_headers", False),
        raw_path=getattr(args, "raw_path", False),
        cookie_jar=getattr(args, "cookie_jar", None) or "",
        session=getattr(args, "session", None) or "",
        body=body,
        body_type=body_type,
        auth_type=auth_type,
        auth_value=auth_value,
        proxy=args.proxy or "",
        max_retries=args.retry,
        retry_delay=args.retry_delay,
        compressed=args.compressed,
        http2=args.http2,
        output_path=args.output or "",
        pretty=args.pretty,
        raw=getattr(args, "raw", False),
        env_file=args.env_file or "",
        follow_redirects=not args.no_redirect,
        verify_ssl=not args.no_verify,
        timeout=args.timeout,
    )


def _persist(
    config: RequestConfig,
    status_code: int | None,
    duration_ms: float,
    repo: HistoryRepo,
    env_vars: dict[str, str] | None = None,
    no_redact: bool = False,
) -> None:
    # Redact secrets before they ever touch disk (1.5). The stored curl is
    # regenerated from the redacted config so it can never leak a token either.
    stored = config if no_redact else redact_config(config, env_vars or {})
    entry = HistoryEntry(
        id=0,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        request=stored,
        status_code=status_code,
        duration_ms=duration_ms,
        curl_cmd=build_curl(stored),
    )
    repo.save(entry)


def _print_curl(curl_cmd: str) -> None:
    _console.print(Syntax(curl_cmd, "bash", theme="monokai", word_wrap=True))


def _delete_history(repo: HistoryRepo, id: int) -> int:
    entry = repo.get_by_id(id)
    if entry is None:
        _console.print(f"[red]No history entry with ID {id}.[/red]")
        return EXIT_USAGE
    repo.delete_by_id(id)
    _console.print(f"[green]Deleted history entry {id}.[/green]")
    return EXIT_OK


def _load_env_file(path: str) -> dict[str, str]:
    vars: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        _console.print(f"[red]Env file not found:[/red] {path}")
        return vars

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            vars[key.strip()] = value.strip().strip('"').strip("'")
    return vars


def _substitute_variables(text: str, env_vars: dict[str, str]) -> str:
    if not env_vars:
        return text

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return env_vars.get(name, match.group(0))

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", replace, text)


def _status_style(status_code: int | None) -> str:
    if status_code is None:
        return "red"
    if status_code < 300:
        return "green"
    if status_code < 400:
        return "yellow"
    return "red"
