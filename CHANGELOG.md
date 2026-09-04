# Changelog

All notable changes to CurlCommander are documented here. This release turns a
basic curl generator into a request builder and API/AppSec testing tool. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [0.2.0]

### Architecture
- **Ordered, case- and duplicate-preserving headers & params.** `HeaderList`
  replaces `dict`, so duplicate `X-Forwarded-For`/`Cookie` headers, HPP query
  params (`?id=1&id=2`) and exact header casing/order survive from input →
  curl → wire → storage.
- **Raw byte-level socket transport** that bypasses httpx normalisation for
  request smuggling, CRLF and path-traversal testing.

### Phase 1 — bug fixes (each with a regression test)
- **1.1** Basic auth now appears in the generated curl (`-u user:pass`); the
  curl reproduces the wire for all four auth types.
- **1.2** `-L` is emitted only when redirects are followed.
- **1.3** A non-default `--timeout` is reflected as `--max-time`.
- **1.4** Lossless replay: the full request is stored as `config_json` and every
  field is rehydrated; replay refuses to send an empty credential.
- **1.5** Secret redaction before persistence (`{{VAR}}` references or REDACTED),
  DB dir/file at `0700`/`0600`, `--no-redact` (warned) and `--reveal`.
- **1.6** Meaningful exit codes: `0` ok, `1` usage, `2` network, `3` assertion,
  `22` HTTP ≥ 400 with `--fail`.
- **1.7** Centralized header/param parsing; `-H "Accept:application/json"` no
  longer silently drops.
- **1.8** Binary-safe `--output` (raw bytes); charset-aware display decoding.
- **1.9** Large response bodies are truncated for display, saved in full.
- **1.10** JSON pretty-printed automatically; `--raw` disables formatting.
- **1.11** The GUI reuses one SQLite connection and closes it.

### Phase 2 — functional gaps
- **2.1** Import curl commands (`--import`, `--import-file`, `--import-clipboard`).
- **2.2** Import raw HTTP request blocks (`--import-raw --host`).
- **2.3** Cookies and sessions (`--cookie`, `--cookie-jar`, `--session`).
- **2.4** Multipart uploads (`-F/--form-file`, controllable filename/type).
- **2.6** Response assertions (`--assert-*`) with `--report json|junit`.
- **2.12** `--version`, `--fail`, `--raw`.
- **2.13** TUI options panel, response tabs (Body/Headers/Raw/Cookies), body
  search, clipboard copy, portable keybindings, env substitution.

### Phase 2B — pentest & API testing
- **2B.1** Full header/param/request-line control, `--no-default-headers`,
  `--raw-path` (byte-faithful, no URL normalisation).
- **2B.2** Raw request transport (`--raw-request`), CL.TE/TE.CL survive.
- **2B.3** Fuzzing (`-w`, `--payloads`, clusterbomb/pitchfork, `--mc/--fc/--ms/
  --fs/--mr`, `--concurrency`, `--rate`) with pluggable encoders (`--encode`).
- **2B.4** Built-in payload library (sqli/xss/ssti/traversal/cmdi) scaffold.
- **2B.6** GraphQL (`--graphql`, introspection), SOAP/XML, gRPC-web, streaming
  (`--stream` for NDJSON/SSE).
- **2B.8** Scope allowlist (`--scope`), `--dry-run`, evidence capture
  (`--evidence`, `--engagement`), visible `--no-verify` warning.

### Phase 3 — engineering quality
- **3.1** GitHub Actions CI: ruff + ruff-format + mypy, a 3.11/3.12/3.13 ×
  Linux/macOS/Windows test matrix with an 80% coverage gate, and pip-audit.
- **3.2** ruff (lint+format), mypy `--strict` on `core/`+`storage/`, pre-commit.
- **3.3** Tests for the runner, main detection, the GUI (Textual pilot), the
  curl round-trip, and that no secret reaches SQLite or the JSON export.
- **3.4** Full package metadata, `LICENSE` (MIT), `CONTRIBUTING.md`.
- **3.5** `install.sh` prefers `uv`/`pipx`, venv fallback, `--break-system-
  packages` only behind `--system`.
- **3.6** SQLite schema migrations via `PRAGMA user_version`.
- **3.7** Structured logging (`--log-file`, `--log-level`) with secret redaction.

## [0.1.0]
- Initial release: curl generation, httpx sending, SQLite history, wizard, TUI.
