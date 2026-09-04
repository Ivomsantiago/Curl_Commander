# Contributing to CurlCommander

Thanks for helping improve CurlCommander. This project is a terminal HTTP
request builder and API/AppSec testing tool; correctness and byte-faithfulness
matter, so changes come with tests.

## Development setup

```bash
uv venv && source .venv/bin/activate     # or: python -m venv .venv
uv pip install -e ".[dev]"               # or: pip install -e ".[dev]"
pre-commit install                       # optional: run checks on commit
```

## Architecture

Strict layering — `core/` must never import from `cli/` or `gui/`:

- `core/` — request model, curl builder/parser, transports (httpx + raw
  socket), redaction, fuzzing, assertions, encoders, scope, evidence.
- `storage/` — SQLite history with `PRAGMA user_version` migrations.
- `cli/` — argparse, orchestration, wizard.
- `gui/` — Textual TUI.

## Before opening a PR

Run the full gate locally — CI runs the same:

```bash
ruff check .
ruff format --check .
mypy                     # strict on core/ and storage/
pytest --cov=curlcommander
```

Guidelines:

- **Every behaviour change ships with a test.** Bug fixes get a regression test
  that fails before and passes after.
- **Keep `mypy --strict` clean** in `core/` and `storage/`; add type hints.
- **No new runtime dependency** without justification; optional features go in
  `[project.optional-dependencies]`.
- **Never persist a secret.** Anything written to the history DB, the JSON
  export, evidence, or logs must go through the redaction layer.
- One focused commit per change, messages prefixed `fix:` / `feat:` / `chore:`
  / `test:` / `docs:`.

## Security testing scope

This tool is for **authorised** security testing. When adding pentest features,
keep the safety rails intact: scope enforcement (`--scope`), the `--no-verify`
warning, and secret redaction are not optional.
