"""Runtime configuration and platform-appropriate storage locations.

The application directory follows OS conventions via platformdirs:
- Windows: ``%LOCALAPPDATA%\\CurlCommander``
- macOS:   ``~/Library/Application Support/CurlCommander``
- Linux:   ``~/.local/share/curlcommander`` (respects ``XDG_DATA_HOME``)

``CURLCOMMANDER_HOME`` overrides it entirely (portable/CI use). A legacy
``~/.curlcommander`` from earlier versions is migrated on first run.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import platformdirs

HISTORY_LIMIT = 30
DEFAULT_TIMEOUT = 30.0
# Max response body rendered to the terminal before truncation (bytes).
# --output always saves the full content regardless of this limit.
DISPLAY_LIMIT_BYTES = 100_000
DEFAULT_METHOD = "GET"
HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
AUTH_TYPES = ["none", "bearer", "basic", "apikey"]
BODY_TYPES = ["none", "json", "form", "raw"]

LEGACY_DIR = Path.home() / ".curlcommander"


def app_dir() -> Path:
    """Resolve the application data directory for this OS (or the override)."""
    override = os.environ.get("CURLCOMMANDER_HOME")
    if override:
        return Path(override)
    # Lowercase name on Linux (XDG convention), CamelCase on Windows/macOS.
    appname = "curlcommander" if sys.platform.startswith("linux") else "CurlCommander"
    return Path(platformdirs.user_data_dir(appname, appauthor=False))


APP_DIR = app_dir()
DB_PATH = APP_DIR / "history.db"

# --- per-engagement data isolation (8.1) -----------------------------------
#
# A single global history.db means every target ever tested, across every
# client and date, lives in one file with no separation — a confidentiality
# problem (NDA/LGPD-style deletion-on-request), not just an organisational
# one. --engagement <name> on a command isolates its history + persisted
# findings under their own file instead of the shared ad-hoc one.

_ENGAGEMENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")


class InvalidEngagementName(ValueError):
    pass


def validate_engagement_name(name: str) -> str:
    """Reject anything that isn't a safe, single, flat path component.

    An engagement name becomes a literal directory name under ``app_dir()``;
    this check is the only thing standing between a free-text --engagement
    value and path traversal (``../../etc``, an absolute path, a separator).
    """
    if not _ENGAGEMENT_NAME_RE.match(name):
        raise InvalidEngagementName(
            f"nome de engajamento inválido: {name!r} — use letras/números/'.'/'_'/'-' "
            "(1-63 caracteres, começando com letra/número, sem espaços ou separadores de caminho)"
        )
    return name


def engagements_dir() -> Path:
    return app_dir() / "engagements"


def engagement_dir(name: str) -> Path:
    return engagements_dir() / validate_engagement_name(name)


def db_path_for(engagement: str | None, default: Path | str) -> Path:
    """The history/validation-results DB path for *engagement*.

    Falls back to *default* — the caller's own DB_PATH — when no engagement
    is given, so call sites stay monkeypatch-friendly in tests: pass your
    module's own ``DB_PATH`` (which a test may have redirected to a tmp
    path) as *default*, never the global constant directly.

    The isolated path is rooted next to *default* (its parent directory),
    not at the global ``app_dir()`` — this is what keeps it test-friendly
    (a monkeypatched ``DB_PATH`` under a tmp dir naturally keeps engagement
    data under that same tmp dir too) while still matching
    ``engagement_dir()``/``list_engagements()`` in the real app, since there
    ``default`` (``config.DB_PATH``) already lives directly under
    ``app_dir()``.
    """
    default_path = Path(default)
    if not engagement:
        return default_path
    return default_path.parent / "engagements" / validate_engagement_name(engagement) / "history.db"


def list_engagements() -> list[str]:
    """Names of every isolated engagement directory that actually holds a DB."""
    d = engagements_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and (p / "history.db").exists())


def migrate_legacy(target: Path | None = None) -> Path | None:
    """Move a legacy ~/.curlcommander into the new location, once.

    No-op when there is no legacy dir, when the target already has a history
    DB, or when the override points back at the legacy path. Best-effort and
    idempotent; returns the destination it migrated to, else None.
    """
    dest = target or APP_DIR
    legacy = LEGACY_DIR
    try:
        if not legacy.is_dir() or legacy.resolve() == dest.resolve():
            return None
        if (dest / "history.db").exists():
            return None  # already migrated or fresh install alongside legacy
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # Merge files rather than clobber an existing (empty) dir.
            for item in legacy.iterdir():
                target_item = dest / item.name
                if not target_item.exists():
                    item.rename(target_item)
        else:
            legacy.rename(dest)
        sys.stderr.write(f"curlcommander: migrated history from {legacy} to {dest}\n")
        return dest
    except OSError:
        return None
