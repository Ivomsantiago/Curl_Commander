import argparse
from typing import NoReturn


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
    imp.add_argument("--host", metavar="URL", help="Base host for --import-raw (e.g. https://target)")
    parser.add_argument("-X", "--method", default="GET", metavar="METHOD", help="HTTP method (default: GET)")
    parser.add_argument("-H", "--header", action="append", dest="headers", default=[], metavar="Key: Value", help="Header (repeatable)")
    parser.add_argument("-p", "--param", action="append", dest="params", default=[], metavar="key=value", help="Query param (repeatable)")
    parser.add_argument("-b", "--body", default="", help="Request body as string")
    parser.add_argument("--body-file", metavar="PATH", help="Read request body from file")
    parser.add_argument("--json", dest="json_body", metavar="JSON", help="JSON body (sets Content-Type automatically)")
    parser.add_argument("--form", dest="form_body", metavar="DATA", help="Form-urlencoded body")
    parser.add_argument("--auth-bearer", metavar="TOKEN", help="Bearer token")
    parser.add_argument("--auth-basic", metavar="USER:PASS", help="Basic auth credentials")
    parser.add_argument("--auth-apikey", metavar="'Header: Value'", help="API key auth")
    parser.add_argument("--proxy", metavar="URL", help="Proxy URL to route the request through")
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
    parser.add_argument("--no-redact", action="store_true", help="Store credentials in clear text in history (unsafe)")
    parser.add_argument("--fail", action="store_true", help="Exit 22 on HTTP status >= 400 (like curl --fail)")
    parser.add_argument("--curl-only", action="store_true", help="Print curl command without sending")
    parser.add_argument("--save", action="store_true", help="Save to history even with --curl-only")
    parser.add_argument("--gui", action="store_true", help="Launch the Textual TUI")
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

    return parser


SUBCOMMANDS: frozenset[str] = frozenset({"history", "replay", "curl", "export-history", "delete-history", "clear-history"})
