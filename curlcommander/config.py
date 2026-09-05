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
import sys
from pathlib import Path

import platformdirs

HISTORY_LIMIT = 30
DEFAULT_TIMEOUT = 30.0
# Max response body rendered to the terminal before truncation (bytes).
# --output always saves the full content regardless of this limit.
DISPLAY_LIMIT_BYTES = 1_000_000
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
