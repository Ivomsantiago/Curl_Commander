import argparse
from typing import NoReturn


def _version() -> str:
    from curlcommander import __version__

    return __version__


class ArgParser(argparse.ArgumentParser):
    """ArgumentParser that exits with code 1 (usage error) instead of 2."""

    def error(self, message: str) -> NoReturn:
        self.print_usage()
        self.exit(1, f"{self.prog}: error: {message}\n")


def build_request_parser() -> argparse.ArgumentParser:
    """Parser used when no subcommand is detected (request / wizard mode)."""
    parser = ArgParser(
        prog="curlcmd",
        description="CurlCommander — visual HTTP request builder and curl generator",
    )
    parser.add_argument("url", nargs="?", help="Target URL")
    imp = parser.add_argument_group("import")
    imp.add_argument("--import", dest="import_curl", metavar="CURL", help="Import a curl command string")
    imp.add_argument("--import-file", metavar="PATH", help="Import a curl command from a file")
    imp.add_argument("--import-clipboard", action="store_true", help="Import a curl command from the clipboard")
    imp.add_argument("--import-raw", metavar="PATH", help="Import a raw HTTP request block (Burp/.http)")
    imp.add_argument("--host", metavar="URL", help="Base host for --import-raw / --raw-request (e.g. https://target)")

    api = parser.add_argument_group("API styles")
    api.add_argument("--graphql", metavar="QUERY", help="Send a GraphQL query (POST JSON)")
    api.add_argument("--graphql-vars", metavar="JSON", help="GraphQL variables as JSON")
    api.add_argument(
        "--graphql-introspection", action="store_true", help="Send introspection query and report if enabled"
    )
    api.add_argument("--xml", metavar="BODY|@FILE", help="Send an XML body (application/xml)")
    api.add_argument("--soap", metavar="BODY|@FILE", help="Send a SOAP/XML body (text/xml)")
    api.add_argument("--soap-action", metavar="URI", help="SOAPAction header value")
    api.add_argument("--soap-envelope", action="store_true", help="Wrap --soap body in a SOAP envelope")
    api.add_argument("--grpc-web", action="store_true", help="Set gRPC-web content-type (use --body-file for bytes)")
    api.add_argument("--stream", action="store_true", help="Stream the response line by line (NDJSON/SSE)")

    raw = parser.add_argument_group("raw / pentest control")
    raw.add_argument("--raw-request", metavar="PATH", help="Send a raw HTTP block byte-for-byte over a socket")
    raw.add_argument("--no-fix-length", action="store_true", help="Never recompute Content-Length for --raw-request")
    raw.add_argument("--raw-path", action="store_true", help="Send the URL path byte-faithful (no normalization)")
    raw.add_argument(
        "--no-default-headers", action="store_true", help="Do not send httpx default headers (UA/Accept/...)"
    )

    opsec = parser.add_argument_group("operational safety")
    opsec.add_argument("--scope", metavar="PATH", help="Allowlist of in-scope hosts/CIDRs; refuse out-of-scope targets")
    opsec.add_argument("--dry-run", action="store_true", help="Show what would be sent on the wire without sending")
    opsec.add_argument("--evidence", metavar="DIR", help="Save raw request+response+metadata to DIR")
    opsec.add_argument("--engagement", metavar="LABEL", help="Authorization/engagement label for evidence")

    fuzz = parser.add_argument_group("fuzzing")
    fuzz.add_argument(
        "-w",
        "--wordlist",
        action="append",
        dest="wordlists",
        default=[],
        metavar="PATH",
        help="Wordlist for FUZZ markers (repeatable)",
    )
    fuzz.add_argument(
        "--payloads",
        action="append",
        dest="payloads",
        default=[],
        metavar="CAT",
        help="Payload category via the catalog (xss/sqli/ssti/lfi/ssrf/...)",
    )
    fuzz.add_argument(
        "--payloads-all",
        action="append",
        dest="payloads_all",
        default=[],
        metavar="CAT",
        help="Payload category from ALL synced sources, deduped",
    )
    fuzz.add_argument(
        "--fuzz-mode", choices=["clusterbomb", "pitchfork"], default="clusterbomb", help="Multi-wordlist mode"
    )
    fuzz.add_argument("--encode", metavar="LIST", help="Encoder chain applied to payloads (e.g. url,base64)")
    fuzz.add_argument("--concurrency", type=int, default=10, metavar="N", help="Concurrent fuzz requests")
    fuzz.add_argument("--rate", type=float, default=0.0, metavar="R", help="Max requests per second (0 = unlimited)")
    fuzz.add_argument("--mc", metavar="CODES", help="Match status codes (comma-separated)")
    fuzz.add_argument("--fc", metavar="CODES", help="Filter out status codes (comma-separated)")
    fuzz.add_argument("--ms", type=int, metavar="N", help="Match response size N bytes")
    fuzz.add_argument("--fs", type=int, metavar="N", help="Filter out response size N bytes")
    fuzz.add_argument("--mr", metavar="REGEX", help="Match body regex")
    parser.add_argument("-X", "--method", default="GET", metavar="METHOD", help="HTTP method (default: GET)")
    parser.add_argument(
        "-H", "--header", action="append", dest="headers", default=[], metavar="Key: Value", help="Header (repeatable)"
    )
    parser.add_argument(
        "-p",
        "--param",
        action="append",
        dest="params",
        default=[],
        metavar="key=value",
        help="Query param (repeatable)",
    )
    parser.add_argument("-b", "--body", default="", help="Request body as string")
    parser.add_argument("--body-file", metavar="PATH", help="Read request body from file")
    parser.add_argument("--json", dest="json_body", metavar="JSON", help="JSON body (sets Content-Type automatically)")
    parser.add_argument("--form", dest="form_body", metavar="DATA", help="Form-urlencoded body")
    parser.add_argument("--auth-bearer", metavar="TOKEN", help="Bearer token")
    parser.add_argument("--auth-basic", metavar="USER:PASS", help="Basic auth credentials")
    parser.add_argument("--auth-apikey", metavar="'Header: Value'", help="API key auth")
    parser.add_argument(
        "--cookie", action="append", dest="cookies", default=[], metavar="k=v", help="Cookie (repeatable)"
    )
    parser.add_argument("--cookie-jar", metavar="PATH", help="Persist/load cookies in a jar file")
    parser.add_argument("--session", metavar="NAME", help="Named session (persistent cookie jar)")
    parser.add_argument(
        "-F",
        "--form-file",
        action="append",
        dest="form",
        default=[],
        metavar="name=@file",
        help="Multipart field/file (repeatable)",
    )
    parser.add_argument("--proxy", metavar="URL", help="Proxy URL to route the request through")
    parser.add_argument("--burp", action="store_true", help="Shortcut for --proxy http://127.0.0.1:8080 --no-verify")
    parser.add_argument("--retry", type=int, default=0, metavar="N", help="Number of retry attempts on network error")
    parser.add_argument("--retry-delay", type=float, default=0.0, metavar="SECONDS", help="Delay between retries")
    parser.add_argument("--compressed", action="store_true", help="Request compressed response")
    parser.add_argument("--http2", action="store_true", help="Use HTTP/2 if supported")
    parser.add_argument("--output", metavar="PATH", default="", help="Save response body to file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print response body (JSON is pretty by default)")
    parser.add_argument("--raw", action="store_true", help="Disable response formatting/pretty-printing")
    parser.add_argument("--env-file", metavar="PATH", help="Load environment variables from a file for substitutions")
    parser.add_argument("--no-redirect", action="store_true", help="Do not follow redirects")
    parser.add_argument("--no-verify", action="store_true", help="Disable SSL certificate verification")
    parser.add_argument("--timeout", type=float, default=30.0, metavar="SECONDS", help="Request timeout (default: 30)")
    asserts = parser.add_argument_group("assertions (test mode)")
    asserts.add_argument("--assert-status", type=int, metavar="N", help="Assert HTTP status equals N")
    asserts.add_argument(
        "--assert-header",
        action="append",
        dest="assert_headers",
        default=[],
        metavar="Name: Value",
        help="Assert header (repeatable)",
    )
    asserts.add_argument(
        "--assert-body-contains",
        action="append",
        dest="assert_body",
        default=[],
        metavar="STR",
        help="Assert body contains STR (repeatable)",
    )
    asserts.add_argument(
        "--assert-jsonpath",
        action="append",
        dest="assert_jsonpath",
        default=[],
        metavar="EXPR",
        help="Assert JSONPath (e.g. '$.user.id==42')",
    )
    asserts.add_argument("--assert-max-ms", type=float, metavar="MS", help="Assert response time under MS milliseconds")
    asserts.add_argument("--report", choices=["json", "junit"], help="Emit an assertion report to stdout")

    parser.add_argument("--no-redact", action="store_true", help="Store credentials in clear text in history (unsafe)")
    parser.add_argument("--fail", action="store_true", help="Exit 22 on HTTP status >= 400 (like curl --fail)")
    parser.add_argument("--curl-only", action="store_true", help="Print curl command without sending")
    parser.add_argument("--save", action="store_true", help="Save to history even with --curl-only")
    parser.add_argument("--gui", action="store_true", help="Launch the Textual TUI")
    parser.add_argument("--log-file", metavar="PATH", help="Write redacted structured logs to PATH")
    parser.add_argument("--log-level", choices=["debug", "info", "warning", "error"], help="Log verbosity")
    parser.add_argument("--version", action="version", version=f"curlcmd {_version()}")
    return parser


def build_subcommand_parser() -> argparse.ArgumentParser:
    """Parser used when a subcommand (history, replay, curl, clear-history) is detected."""
    parser = ArgParser(
        prog="curlcmd",
        description="CurlCommander — subcommands",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    history_p = subparsers.add_parser("history", help="List request history")
    history_p.add_argument("--reveal", action="store_true", help="Resolve {{VAR}} secret references")

    replay_p = subparsers.add_parser("replay", help="Replay a history entry by ID")
    replay_p.add_argument("id", type=int, help="History entry ID")

    curl_p = subparsers.add_parser("curl", help="Print curl command for a history entry")
    curl_p.add_argument("id", type=int, help="History entry ID")
    curl_p.add_argument("--reveal", action="store_true", help="Resolve {{VAR}} secret references")

    export_p = subparsers.add_parser("export-history", help="Export history to JSON")
    export_p.add_argument("-o", "--output", default="history.json", metavar="PATH", help="Output JSON file path")
    export_p.add_argument("--reveal", action="store_true", help="Resolve {{VAR}} secret references")

    delete_p = subparsers.add_parser("delete-history", help="Delete a history entry by ID")
    delete_p.add_argument("id", type=int, help="History entry ID")

    subparsers.add_parser("clear-history", help="Clear all history")

    # payloads sync / update / list / search / show
    payloads_p = subparsers.add_parser("payloads", help="Manage payload sources and catalog")
    p_sub = payloads_p.add_subparsers(dest="payloads_cmd", required=True)
    p_sync = p_sub.add_parser("sync", help="Clone/update a payload source")
    p_sync.add_argument("source", nargs="?", help="Source name (default: all)")
    p_sub.add_parser("update", help="Update all synced sources")
    p_list = p_sub.add_parser("list", help="List catalog categories / synced sources")
    p_list.add_argument("--category", metavar="CAT", help="List files backing a category")
    p_search = p_sub.add_parser("search", help="Search wordlist filenames")
    p_search.add_argument("term", help="Substring to search for")
    p_show = p_sub.add_parser("show", help="Preview a category's payloads")
    p_show.add_argument("category", help="Category name")
    p_show.add_argument("--limit", type=int, default=20, help="Max lines to show")
    p_show.add_argument("--count", action="store_true", help="Only print the total count")
    p_show.add_argument("--all", action="store_true", dest="all_sources", help="Use all synced sources")

    # discover (content discovery via the fuzz engine)
    disc = subparsers.add_parser("discover", help="Content discovery / dirbusting against a URL")
    disc.add_argument("url", help="Base URL")
    disc.add_argument("-w", "--wordlist", action="append", dest="wordlists", default=[], metavar="SPEC")
    disc.add_argument("--payloads", action="append", dest="payloads", default=[], metavar="CAT")
    disc.add_argument("-e", "--extensions", metavar="EXT", help="Comma-separated extensions (php,bak,old)")
    disc.add_argument("--recurse", type=int, default=0, metavar="DEPTH", help="Shallow recursion depth")
    disc.add_argument("--concurrency", type=int, default=20, metavar="N")
    disc.add_argument("--rate", type=float, default=0.0, metavar="R")
    disc.add_argument("--mc", metavar="CODES")
    disc.add_argument("--fc", metavar="CODES", default="404")
    disc.add_argument("--ms", type=int, metavar="N")
    disc.add_argument("--fs", type=int, metavar="N")
    disc.add_argument("--mr", metavar="REGEX")
    disc.add_argument("--scope", metavar="PATH")
    disc.add_argument("--no-verify", action="store_true")
    disc.add_argument("--timeout", type=float, default=30.0)

    # validate (browser-executed / HTTP vulnerability validators)
    val = subparsers.add_parser("validate", help="Validate a vulnerability (browser/HTTP)")
    val.add_argument("kind", choices=["xss", "cors", "open-redirect", "clickjacking", "csrf"])
    val.add_argument("url", help="Target URL (use §PAYLOAD§/§DEST§ markers where relevant)")
    val.add_argument("--engagement", metavar="LABEL", help="Authorization label (required)")
    val.add_argument("--scope", metavar="PATH")
    val.add_argument("--origin", metavar="ORIGIN", default="https://evil.example", help="CORS attacker origin")
    val.add_argument("--headed", action="store_true", help="Show the browser window")
    val.add_argument("--evidence", metavar="DIR", help="Save screenshot/DOM/HAR here")
    val.add_argument("--no-verify", action="store_true")
    val.add_argument("--timeout", type=float, default=30.0)

    # bounty-scan (discover + per-category fuzz, consolidated by severity)
    bounty = subparsers.add_parser("bounty-scan", help="Chained discovery + payload fuzz profile")
    bounty.add_argument("url", help="Target URL")
    bounty.add_argument("--scope", metavar="PATH")
    bounty.add_argument("--engagement", metavar="LABEL", help="Authorization label (required)")
    bounty.add_argument("--categories", metavar="LIST", default="xss,sqli,traversal,ssti")
    bounty.add_argument("--concurrency", type=int, default=10)
    bounty.add_argument("--rate", type=float, default=0.0)
    bounty.add_argument("--no-verify", action="store_true")
    bounty.add_argument("--timeout", type=float, default=30.0)

    return parser


SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "history",
        "replay",
        "curl",
        "export-history",
        "delete-history",
        "clear-history",
        "payloads",
        "discover",
        "bounty-scan",
        "validate",
    }
)
