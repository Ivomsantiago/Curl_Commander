# CurlCommander

A terminal HTTP request builder, `curl` generator, and API/AppSec testing tool.
Build and replay requests, generate a faithful `curl`, import from DevTools or
Burp, fuzz, assert, and drive raw byte-level requests — from one entrypoint,
`curlcmd`.

Built for analysts and engineers who need requests reliable enough to paste into
a pentest report, expressive enough to test any API style (REST, GraphQL,
SOAP/XML, gRPC-web, legacy forms), and scriptable enough to run in CI.

Python 3.11+ · `httpx` · `rich` · `prompt_toolkit` · `textual`.

---

## 1. Installation

```bash
bash install.sh            # uv tool / pipx, or a local .venv
```

The installer prefers isolated installs (`uv tool install`, then `pipx`), falls
back to a local `.venv`, and only touches the system Python with
`--break-system-packages` if you pass `--system` and confirm.

Optional extras: `pip install "curlcommander[socks]"` (SOCKS proxy),
`"[clipboard]"` (pyperclip). Run `curlcmd --version` to verify.

---

## 2. Security

This is the most important section — the history database stores request
metadata, and without care that becomes a dump of client credentials.

**What is redacted (default).** Before anything is written to the history DB,
the JSON export, evidence files, or logs, secrets are removed:

- Bearer/Basic/API-key auth values, `Authorization`/`Proxy-Authorization`,
  `Cookie`/`Set-Cookie`, `X-API-Key` and similar headers, and proxy credentials.
- Secrets that came from `--env-file` are stored as **resolvable references**
  (`{{VAR}}`), so they can be replayed later; everything else secret is replaced
  with `«REDACTED»` and is genuinely discarded.
- The stored `curl` is regenerated from the redacted request, so it never leaks.

**What is not redacted.** Method, URL path, hostnames, non-sensitive headers,
query params and bodies are stored as-is (a secret embedded directly in a URL
query or body is your responsibility). `--no-redact` disables redaction entirely
and prints a warning.

**Revealing.** `curlcmd history --reveal`, `curlcmd curl <id> --reveal` and
`export-history --reveal` resolve `{{VAR}}` references from the current
environment. `«REDACTED»` values are unrecoverable by design.

**Storage location.** History lives in the OS data dir — `%LOCALAPPDATA%\CurlCommander`
(Windows), `~/Library/Application Support/CurlCommander` (macOS),
`~/.local/share/curlcommander` (Linux, respects `XDG_DATA_HOME`). Set
`CURLCOMMANDER_HOME` to override it (portable/CI use). A legacy
`~/.curlcommander` from earlier versions is migrated automatically on first run.

**File permissions.** The app dir is created `0700` and `history.db` `0600`
(session cookie jars `0600`) on POSIX. **On Windows** `chmod` only toggles the
read-only bit — it does not restrict other local users — so on Windows the real
protection for the history is **secret redaction** (enabled by default); do not
disable it with `--no-redact` on a shared machine.

**Operational safety for pentests.** `--scope scope.txt` refuses any target not
in the allowlist. `--dry-run` shows the exact bytes without sending.
`--no-verify` always prints a visible warning. `--evidence DIR --engagement
LABEL` saves raw request + response + metadata for the report.

---

## 3. CLI

```bash
curlcmd https://httpbin.org/get                         # simple GET
curlcmd -X POST --json '{"name":"ada"}' https://api/x   # POST JSON
curlcmd --auth-bearer $TOKEN -H "Accept: application/json" https://api/me
curlcmd -H "X-Forwarded-For: 1.1.1.1" -H "X-Forwarded-For: 2.2.2.2" https://x  # dup headers
curlcmd -p "id=1" -p "id=2" https://x                   # HPP (duplicate params)
curlcmd -X POST -F "file=@shell.php;type=image/png" https://x/upload
curlcmd --curl-only -X POST --json '{"id":1}' https://api/x   # print curl only
```

### AppSec flow: DevTools → import → edit → resend → assert

```bash
# 1. Copy as cURL from DevTools/Burp, import and resend through Burp:
curlcmd --import 'curl "https://api.x/me" -H "Cookie: s=abc" --data-raw "{}"' --burp

# 2. Import a raw Burp Repeater block, retargeted at another host:
curlcmd --import-raw request.txt --host https://staging.target

# 3. Validate a fix in CI (exit 3 on failure, junit for the pipeline):
curlcmd --assert-status 200 --assert-header "X-Frame-Options: DENY" \
        --assert-jsonpath '$.user.id==42' --assert-max-ms 500 \
        --report junit https://api.x/me
```

### Fuzzing

```bash
curlcmd -w words.txt "https://x/FUZZ" --mc 200,301 --fs 0 --concurrency 20 --rate 10
curlcmd --payloads sqli "https://x/item?id=FUZZ" --mr "SQL syntax"
curlcmd -w users.txt -w pass.txt --fuzz-mode pitchfork "https://x/FUZZ1:FUZZ2"
curlcmd --payloads traversal --encode url,url "https://x/file?p=FUZZ"   # double-url
```

### Raw / pentest control

```bash
curlcmd --raw-path "https://x/a/../../etc/passwd"        # path sent byte-faithful
curlcmd --no-default-headers -H "Host: internal" https://x
curlcmd --raw-request smuggle.txt --host https://target  # CL.TE/TE.CL, byte-for-byte
curlcmd --scope scope.txt --evidence out/ --engagement ENG-2026-07 https://x/y
```

### API styles

```bash
curlcmd --graphql '{ me { id } }' https://x/graphql
curlcmd --graphql-introspection https://x/graphql        # report if enabled
curlcmd --soap @envelope.xml --soap-action "urn:Login" https://x/svc
curlcmd --stream https://x/events                        # NDJSON / SSE
```

### History

```bash
curlcmd history [--reveal]        # list (redacted by default)
curlcmd replay <id>              # re-send (resolves {{VAR}} from env)
curlcmd curl <id> [--reveal]     # print the stored curl
curlcmd export-history -o h.json [--reveal]
curlcmd delete-history <id>
curlcmd clear-history
```

### Flags

| Flag | Description |
|------|-------------|
| `-X, --method` | HTTP method (any token; not validated) |
| `-H, --header` | Header `Key: Value` (repeatable, duplicates preserved) |
| `-p, --param` | Query param `key=value` (repeatable, HPP-capable) |
| `-b, --body` / `--body-file` | Raw body / body from file |
| `--json` / `--form` | JSON / form-urlencoded body |
| `--auth-bearer` / `--auth-basic` / `--auth-apikey` | Auth |
| `--cookie` / `--cookie-jar` / `--session` | Cookies and named sessions |
| `-F, --form-file` | Multipart field/file `name=@path[;type=;filename=]` |
| `--proxy` | Proxy URL (`http://127.0.0.1:8080`) |
| `--retry` / `--retry-delay` / `--compressed` / `--http2` | Transport |
| `--output` | Save raw response bytes to a file |
| `--raw` / `--pretty` | Disable / force display formatting |
| `--env-file` | Load `{{VAR}}` substitutions from a file |
| `--no-redirect` / `--no-verify` / `--timeout` | Request options |
| `--fail` | Exit 22 on HTTP ≥ 400 |
| `--no-redact` / `--reveal` | Secret redaction controls |
| `--import` / `--import-file` / `--import-clipboard` | Import curl |
| `--import-raw` / `--host` | Import a raw HTTP block |
| `--assert-status/-header/-body-contains/-jsonpath/-max-ms` | Assertions |
| `--report json\|junit` | Assertion report |
| `-w, --wordlist` / `--payloads` | Fuzz wordlist / built-in payloads |
| `--fuzz-mode` / `--encode` / `--concurrency` / `--rate` | Fuzz control |
| `--mc/--fc/--ms/--fs/--mr` | Fuzz match/filter (code/size/regex) |
| `--raw-path` / `--raw-request` / `--no-default-headers` | Raw control |
| `--graphql[-vars/-introspection]` / `--xml` / `--soap[-action/-envelope]` | API styles |
| `--grpc-web` / `--stream` | gRPC-web / streaming |
| `--scope` / `--dry-run` / `--evidence` / `--engagement` | Operational safety |
| `--log-file` / `--log-level` | Redacted logging |
| `--curl-only` / `--save` / `--gui` / `--version` | Misc |

Exit codes: `0` ok · `1` usage/parse · `2` network/DNS/TLS/timeout ·
`3` assertion failed · `22` HTTP ≥ 400 with `--fail`.

---

## 4. GUI (TUI)

```bash
curlcmd --gui
```

Request panel (method/URL/headers/params/body/auth **and** options: proxy,
timeout, retries, verify, redirects), a live-updating generated-curl panel, a
tabbed response (Body / Headers / Raw / Cookies) with body search and save, and
a history table (replay / show-curl / delete).

| Key | Action |
|-----|--------|
| `Ctrl+S` | Send (portable; `Ctrl+Enter` also works where the terminal supports it) |
| `Ctrl+Y` | Copy generated curl to clipboard |
| `Ctrl+X` | Cancel in-flight request |
| `Ctrl+L` | Clear form · `Ctrl+H` History · `Ctrl+Q` Quit |

`{{VAR}}` references in the form are resolved from the environment on send.

---

## 5. History storage

Requests are stored in the OS data dir (see Storage location above) as
`history.db` (SQLite, `0600` on POSIX). The full
request is kept as a redacted `config_json` snapshot so replay is lossless;
schema upgrades run automatically via `PRAGMA user_version`.

---

## 6. Development

```bash
uv pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov=curlcommander
```

`core/` never imports from `cli/` or `gui/`. See `CONTRIBUTING.md`.

---

## 7. Roadmap

- Response diffing between history entries (`diff`), stored response bodies.
- Detailed timing (DNS/connect/TLS/TTFB) and redirect-chain view.
- Assisted vuln testing (reflection heuristics, OAST), auth-bypass/IDOR matrices.
- mTLS (`--cert/--key/--cacert`), `--resolve`, `--unix-socket`, pinning.
- Postman/collection export, request collections and environments.
