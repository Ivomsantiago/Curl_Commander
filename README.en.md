# CurlCommander

**🌐 Language:** **English** · [Português](README.md)

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/Ivomsantiago/Curl_Commander/actions/workflows/ci.yml/badge.svg)](https://github.com/Ivomsantiago/Curl_Commander/actions/workflows/ci.yml)
[![Releases](https://img.shields.io/github/v/release/Ivomsantiago/Curl_Commander?display_name=tag&sort=semver)](https://github.com/Ivomsantiago/Curl_Commander/releases)

A terminal HTTP request builder, `curl` generator, and API/AppSec testing tool.
Build and replay requests, generate a faithful `curl`, import from DevTools or
Burp, fuzz, assert, and drive raw byte-level requests — from one entrypoint,
`curlcmd` (also installed as `curlcommander`, an alias matching the package
name).

Built for analysts and engineers who need requests reliable enough to paste into
a pentest report, expressive enough to test any API style (REST, GraphQL,
SOAP/XML, gRPC-web, legacy forms), and scriptable enough to run in CI.

Python 3.11+ · `httpx` · `rich` · `prompt_toolkit` · `textual`.

![CurlCommander demo](https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/docs/demo.gif)

---

## Why not just curl?

`curl` is unbeatable for a one-off request or a script. It struggles when the
work is iterative, stateful, repeatable and investigative — the daily grind of
API testing and bug bounty hunting. The table below lists only what plain curl
makes painful or impossible, with the real command/shortcut here (`GUI` = in
the `curlcmd --gui` interface; `CLI` = on the command line):

| Task | Plain curl | CurlCommander |
|------|-----------|---------------|
| Edit one header and resend | rewrite the whole line | **GUI** Repeater tab: edit and resend; resend history in the tab |
| Fuzzing with positions and filters | separate `ffuf`/`wfuzz` | **GUI** Intruder tab (`§mark§` a position, 4 modes, sortable grid) · **CLI** `-w list "…/FUZZ" --mc 200` |
| Intercepting the browser | separate Burp/mitmproxy | **GUI** Proxy tab: live capture + "send to Repeater/Intruder" |
| Analyzing response security | nothing | **GUI** Analyze button (headers/cookies/CORS/errors → candidates) |
| Remembering what was sent | the shell forgets | **CLI** `curlcmd history` (searchable SQLite), `replay <id>` |
| Same request across dev/staging/prod | copy-paste | **CLI** `{{VAR}}` + `--env-file` |
| Testing (assert + exit code + JUnit) | doesn't exist | **CLI** `--assert-status/-header/-jsonpath --report junit` |
| Not leaking a token into history | ends up in `~/.bash_history` | secret redaction before persisting (default) |
| Confirming a real XSS | impossible | **CLI** `validate xss … --engagement` (real browser, `[browser]` extra) |

Examples that actually run:

```bash
# fuzzing with a status filter — plain curl would need ffuf/xargs:
curlcmd -w words.txt "https://target/FUZZ" --mc 200,301 --fc 404

# test a response and fail the pipeline (exit 3) — curl has no assert:
curlcmd --assert-status 200 --assert-jsonpath '$.user.id==42' --report junit https://api/x/me

# open the "Burp in a TUI" interface (Repeater/Intruder/Proxy):
curlcmd --gui
```

---

## Table of contents

1. [Installation](#1-installation)
2. [Security](#2-security)
3. [CLI](#3-cli)
4. [GUI (TUI)](#4-gui-tui)
5. [History storage](#5-history-storage)
6. [Bug bounty — payloads → fuzz → discover](#6-bug-bounty--payloads--fuzz--discover)
7. [Browser validation & intercepting proxy](#7-browser-validation--intercepting-proxy)
8. [Development](#8-development)
9. [Roadmap](#9-roadmap)

---

## 1. Installation

**One line (recommended):**

```bash
# Linux/macOS
curl -fsSL https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.sh | sh
```

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.ps1 | iex
```

The remote installer picks the best method available — `uv tool` → `pipx` → a
managed venv with a `curlcmd` shim — resolves your PATH, is idempotent, and
supports `--yes`/`-Yes` for scripts/CI.

<details>
<summary>Other install methods</summary>

| Method | Command | OS | When to use |
|--------|---------|----|-------------|
| **Standalone binary** | download `curlcmd`/`curlcmd.exe` from Releases | Win/Lin/mac | No Python needed |
| winget | `winget install Ivomsantiago.CurlCommander` | Windows | Windows package manager |
| Scoop | `scoop install curlcommander` | Windows | Scoop bucket |
| `curlcmd.pyz` | download the `.pyz`, `python curlcmd.pyz` | any | Have Python, want one file |
| pipx | `pipx install curlcommander` | any | Isolated user install, on PATH |
| uv | `uv tool install curlcommander` | any | Same, faster |
| pip (dev) | `pip install -e ".[dev]"` | any | Developing/contributing |

The bundled `install.sh` / `install.ps1` (run from a checkout) prefer isolated
installs and only touch the system Python with `--break-system-packages`/`-System`
after confirmation.

</details>

### First run: `setup` and `doctor`

```bash
curlcmd setup            # confirm the base + show what optional features exist
curlcmd setup --all      # install every optional feature and the payload sources
curlcmd setup --browser  # just the browser validators (Playwright + Chromium)
curlcmd doctor           # diagnose the install; add --fix to install what's missing
```

Optional extras are installed by `curlcmd setup` (or manually:
`pip install "curlcommander[browser]"` and `playwright install chromium`,
`"[proxy]"`, `"[socks]"`, `"[clipboard]"`). `curlcmd --version` shows the version
and how it was installed. Update with `curlcmd self-update`.

### Standalone binary (no Python required)

Download `curlcmd` / `curlcmd.exe` for your OS from the
[Releases](https://github.com/Ivomsantiago/Curl_Commander/releases) page, verify
the checksum against `SHA256SUMS`, and run it directly:

```bash
chmod +x curlcmd && ./curlcmd --version          # Linux/macOS
.\curlcmd.exe --version                           # Windows (PowerShell)
```

Build it yourself with `pip install -e ".[build-exe]" && pyinstaller packaging/curlcmd.spec`
(output in `dist/`). A single-file `curlcmd.pyz` (needs Python, no install) is
also available via `pip install -e ".[build-pyz]" && shiv -c curlcmd -o curlcmd.pyz .`.

> **Antivirus note.** PyInstaller binaries occasionally trigger a false positive
> on Windows Defender/SmartScreen. Verify the published SHA256, or install via
> `pipx`/`pip` instead if your environment blocks unsigned binaries.

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

A line prefixed with `!` in `scope.txt` **excludes** a host, even if it also
matches a broader wildcard in the allowlist — the exclusion always wins over
the allow, regardless of line order in the file. Useful when a specific
subdomain (staging, a third-party panel, etc.) falls under the same wildcard
as the target but must never be touched:

```text
# scope.txt
*.karwei.nl
!horrenconfigurator.karwei.nl
```

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

### Auth macro (automated login + session refresh)

A login macro (JSON/YAML) authenticates on its own and re-authenticates when the
session dies mid-fuzz — single-flight refresh (a burst of 401s triggers one
login). Applies to single requests, `discover` and `bounty-scan`; mutually
exclusive with `--auth-bearer/--auth-basic/--auth-apikey`.

```bash
curlcmd --auth-macro login.json "https://api/me"
curlcmd discover https://t -w seclists:... --auth-macro login.json
# apps that return 200 with a "session expired" HTML page:
curlcmd --auth-macro login.json --session-die-regex "session expired" "https://api/me"
```

The macro extracts a token (mini-JSONPath, or `jsonpath-ng` via the `[auth]`
extra) and/or cookies; `backend: "browser"` logs in through a real Chromium (the
`[browser]` extra) for JS/CSRF logins. See the PT-BR README for the JSON shape.

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

### WebSocket (extra `[ws]`)

The same fuzzing engine (clusterbomb/pitchfork, filters, anomaly flagging) runs
over WebSocket — only the transport changes. `connect` opens an interactive
session; `fuzz` swaps the `FUZZ` marker in the message template for each
payload, one reply per send.

```bash
curlcmd ws connect wss://target/socket
curlcmd ws fuzz wss://target/socket --message '{"cmd":"FUZZ"}' -w payloads.txt --mr '"error"'
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

### Import collections (OpenAPI / Postman)

Load a whole spec into history as replayable requests. Wherever the spec has no
example, the field becomes a `FUZZ` marker — ready for the fuzzer. Each request
is tagged with its provenance (`origin`, e.g. `openapi:api.yaml`).

```bash
curlcmd import openapi api.yaml --out collection.json       # OpenAPI 3.0/3.1
curlcmd import postman collection.json --env env.json       # resolves {{var}} from the env
curlcmd history                                             # see what was imported
```

> `securitySchemes` (bearer/basic/apiKey) map to `auth_type`/`auth_value`; secrets
> resolved from a Postman environment are redacted before they touch history.

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

**Per-engagement isolation.** Without `--engagement`, everything lands in the
shared `history.db` (ad-hoc use). With `--engagement NAME` — on any command
that already accepts the flag (a normal request, `validate`, `bounty-scan`,
`proxy`, `report`, `history`/`replay`/`curl`/`export-history`/`delete-history`/
`clear-history`) — history **and** persisted findings are isolated into
`<data dir>/engagements/NAME/history.db`, one file per client/engagement. This
is a confidentiality boundary, not just organization: at the end of an
engagement you can delete one client's data without touching anyone else's.

```bash
curlcmd engagement list                    # isolated engagements + row counts
curlcmd engagement delete client-x         # deletes that engagement's whole history.db (history + findings)
```

> `engagement delete` only removes the isolated `history.db` (history +
> findings). If you also used `--evidence PATH` pointing somewhere else, that
> directory is untouched — you chose it, and it may not be exclusive to this
> engagement.

---

## 6. Bug bounty — payloads → fuzz → discover

Payload sources (SecLists, PayloadsAllTheThings, FuzzDB) are synced on demand,
not vendored. Point at an existing checkout with `SECLISTS_PATH` /
`CURLCOMMANDER_PAYLOADS` instead of syncing.

```bash
curlcmd payloads sync seclists          # shallow, sparse clone into the data dir
curlcmd payloads list                    # categories + synced sources
curlcmd payloads search common           # find wordlist files
curlcmd payloads show xss --count        # size a fuzz run

# Resolve by intent or by source path — one fuzz engine, existing filters:
curlcmd --payloads xss "https://t/s?q=FUZZ" --mr "alert\("
curlcmd -w seclists:Discovery/Web-Content/common.txt "https://t/FUZZ" --fc 404
curlcmd --payloads-all sqli --encode url "https://t/i?id=FUZZ"   # all sources, deduped

# Content discovery (dirbusting) and a chained profile:
curlcmd discover https://t -w seclists:Discovery/Web-Content/raft-medium-directories.txt -e php,bak --recurse 1
curlcmd bounty-scan https://t/page --engagement ENG-2026 --categories xss,sqli,traversal
```

`bounty-scan` consolidates anomalies into severity-ranked **candidates to
investigate** — never confirmations. Confirm them in a browser (below).

## 7. Browser validation & intercepting proxy

Heavy deps are optional extras that degrade with a clear message:

```bash
pip install "curlcommander[browser]" && playwright install chromium   # validators
pip install "curlcommander[proxy]"                                     # proxy
```

**Validate** moves a reflected candidate to CONFIRMED by executing it in a real
browser (unique per-test canary → no false positives). Every navigation is
scope-checked and requires `--engagement`.

```bash
curlcmd validate xss "https://t/s?q=§PAYLOAD§" --engagement ENG --evidence out/
curlcmd validate clickjacking https://t/panel --engagement ENG
curlcmd validate cors https://api.t/data --origin https://evil.example --engagement ENG
curlcmd validate open-redirect "https://t/r?next=§DEST§" --engagement ENG
```

`--evidence DIR` saves a screenshot, the DOM, a HAR and a Playwright trace.

**Authenticated validation.** Anonymous CORS is rarely exploitable — the
real-impact scenario is the same bug behind a login. `--cookie k=v`
(repeatable), `--auth-bearer TOKEN` and `-H`/`--header` (repeatable) apply to
all five HTTP/browser kinds (`cors`, `open-redirect`, `xss`, `clickjacking`,
`csrf`): for `cors`/`open-redirect` they go into the HTTP request headers;
for the browser validators the cookie is injected into the Playwright
context before framing/submitting/navigating, and the extra headers apply to
the whole context:

```bash
curlcmd validate cors https://api.t/data --origin https://evil.example \
  --cookie session=abc123 --auth-bearer $TOKEN --engagement ENG
curlcmd validate clickjacking https://t/admin-panel --cookie session=abc123 --engagement ENG
```

**Blind SSRF via out-of-band** (the `[oob]` extra): confirms blind SSRF/XXE/RCE —
effects invisible in the HTTP response — by making the target connect to a host
you control (the Interactsh protocol: RSA-2048 + AES-256-CFB). DNS-only vs a full
HTTP connection are reported as distinct findings.

```bash
curlcmd validate ssrf "https://t/fetch?url=FUZZ_OOB" --engagement ENG --i-understand-oob
curlcmd validate ssrf "https://t/fetch" --param url --interactsh-server oob.my-lab.com --engagement ENG
```

The target's connection metadata transits the Interactsh server; use
`--interactsh-server` (your own infra) for real engagements — the public server
requires `--i-understand-oob`. The callback URL is **not** the target.

**IDOR / BOLA via authorization correlation.** Does the same URL respond
differently depending on **who** authenticates? For each `RESOURCE_ID`, the same
request is sent as identity A (baseline owner) and as B (attacker) — only the
auth changes — and the bodies are compared. B getting a `200` structurally equal
to A's is **confirmed**; `401/403/404` is **blocked**; the middle ground is
**suspect** (needs a human). `--fuzz-range` measures how many records B can
actually reach.

```bash
curlcmd validate idor "https://api/orders/RESOURCE_ID" --ids 101,102,103 \
        --auth-a owner.json --auth-b attacker.json --engagement ENG
curlcmd validate idor "https://api/orders/RESOURCE_ID" --ids 101 \
        --auth-a owner.json --auth-b attacker.json --fuzz-range 1000-1050 --engagement ENG
```

**Engagement report.** Every `validate … --engagement ENG` records the
validated finding; `bounty-scan --engagement ENG` candidates are also
persisted (never as a confirmation), and any normal request run with
`--engagement ENG` is logged against that engagement too. `report` aggregates
all of it into a single HTML, grouped by severity for confirmed findings,
with a separate section for non-conclusive/candidate results and an appendix
listing the requests sent — repro (`curl`), evidence and remediation. Every
target-derived value is redacted (URL, headers, cookies, **and** the free-form
`evidence` content, e.g. a raw request captured via Interactsh) before it
ever touches disk, not just in the HTML — ready to share.

```bash
curlcmd report --engagement ENG --out report.html
```

**Recon (subfinder/httpx/nuclei/katana).** curlcmd already covers "I have a
URL, let's attack it" well — the phase before that (surface enumeration) is
orchestrated through the real ProjectDiscovery binaries, never reimplemented
in Python: detected on `PATH` (`curlcmd doctor` flags presence/absence;
**curlcmd never installs them**, that stays a manual `go install ...` step),
run via `asyncio.create_subprocess_exec` (never a shell string), and streamed
as JSON/JSONL line by line — never text-scraping. Scope is enforced *before*
anything touches the network: `subfinder`/`katana` refuse a single
out-of-scope target (the same hard refusal as `validate`/`proxy`);
`httpx`/`nuclei` filter the host/URL list *before* handing it to the binary —
an out-of-scope host is never even probed, only dropped and counted.

```bash
curlcmd recon subfinder -d target.com --scope scope.txt --out subs.jsonl
curlcmd recon httpx -l subs.txt --scope scope.txt --out live.jsonl
curlcmd recon nuclei -l urls.txt --severity medium,high,critical --scope scope.txt
curlcmd recon katana -u https://target.com --scope scope.txt --out crawl.jsonl
```

> If the Python `httpx` package (the HTTP client, unrelated) also exposes an
> `httpx` executable on your `PATH`, it can collide with ProjectDiscovery's
> `httpx` — curlcmd resolves it via `PATH` (`shutil.which`), so check
> `curlcmd doctor` if the probe behaves unexpectedly.

**Proxy** — an intercepting HTTPS proxy with its own CA, match-and-replace, and
scope-gated capture into history:

```bash
curlcmd proxy --ca                       # print the CA path + install/removal guidance
curlcmd proxy --port 8080 --scope scope.txt --engagement ENG \
        --replace 'resp:secret==>«X»' --launch-browser
```

> **CA warning.** Installing the proxy CA in your OS/browser lets it decrypt
> your TLS — trust it only for testing and **remove it afterwards**. Only
> in-scope hosts are intercepted; everything else is tunnelled without
> inspection. The standalone binary does **not** bundle Chromium/mitmproxy —
> install the extras separately for browser/proxy mode.

---

## 8. Development

```bash
uv pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest --cov=curlcommander
```

`core/` never imports from `cli/` or `gui/`. See `CONTRIBUTING.md`.

---

## 9. Roadmap

- Response diffing between history entries (`diff`), stored response bodies.
- Detailed timing (DNS/connect/TLS/TTFB) and redirect-chain view.
- Assisted vuln testing (reflection heuristics, OAST), auth-bypass/IDOR matrices.
- mTLS (`--cert/--key/--cacert`), `--resolve`, `--unix-socket`, pinning.
- Postman/collection export, request collections and environments.

## Changelog

See [CHANGELOG.md](https://github.com/Ivomsantiago/Curl_Commander/blob/main/CHANGELOG.md) for every version and the full change history.
