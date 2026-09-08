"""Single engagement config file (8.4): one `--config` instead of repeating
``--engagement``/``--scope``/``--auth-macro``/``--proxy`` on every subcommand.

A real engagement today means retyping the same handful of flags on every
`curlcmd` invocation, across possibly dozens of commands over its lifetime —
and a typo in ``--engagement`` silently creates a second, distinct engagement
(it's a free-text string keyed only by exact match) with no error. A TOML
file read once removes both problems: it is the single place "which
engagement am I in" is spelled, and its fields are strictly *defaults* —
whatever the user actually typed on the command line always wins, never the
file, which is the smaller-blast-radius rule ("what you type now beats a
file you might have forgotten you pointed at").

Parsed with the stdlib ``tomllib`` (Python 3.11+, already the project's
floor) rather than the already-a-dependency ``pyyaml`` — the brief's own
example is TOML syntax, and this avoids adding a write-capable YAML round
trip for a file curlcmd only ever reads.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class EngagementConfigError(RuntimeError):
    """Raised for a --config file that doesn't exist or doesn't parse."""


@dataclass
class EngagementConfig:
    name: str = ""
    scope_file: str = ""
    auth_macro: str = ""
    proxy: str = ""
    wordlist_source: str = ""


def load_engagement_config(path: str | Path) -> EngagementConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise EngagementConfigError(f"não foi possível ler a config de engajamento {path!r}: {exc}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise EngagementConfigError(f"config de engajamento inválida em {path!r}: {exc}") from exc

    engagement = data.get("engagement", {})
    wordlists = data.get("wordlists", {})
    if not isinstance(engagement, dict) or not isinstance(wordlists, dict):
        raise EngagementConfigError(
            f"config de engajamento inválida em {path!r}: [engagement] e [wordlists] devem ser tabelas TOML"
        )
    return EngagementConfig(
        name=str(engagement.get("name", "")),
        scope_file=str(engagement.get("scope_file", "")),
        auth_macro=str(engagement.get("auth_macro", "")),
        proxy=str(engagement.get("proxy", "")),
        wordlist_source=str(wordlists.get("default_source", "")),
    )


def apply_defaults(args: object, cfg: EngagementConfig) -> None:
    """Fill in ``args`` attributes from *cfg*, only where the CLI left them unset.

    Never overwrites a value the user actually passed on the command line —
    an explicit ``--engagement``/``--scope``/``--auth-macro``/``--proxy``
    always wins over the file, regardless of --config's position in argv.
    """
    if cfg.name and not getattr(args, "engagement", None):
        args.engagement = cfg.name  # type: ignore[attr-defined]
    if cfg.scope_file and not getattr(args, "scope", None):
        args.scope = cfg.scope_file  # type: ignore[attr-defined]
    if cfg.auth_macro and not getattr(args, "auth_macro", None):
        args.auth_macro = cfg.auth_macro  # type: ignore[attr-defined]
    if cfg.proxy and not getattr(args, "proxy", None):
        args.proxy = cfg.proxy  # type: ignore[attr-defined]
