import os
import sqlite3
from pathlib import Path

# Base (v1) table. Kept for fast list/filter queries; the full request is also
# stored as config_json from v2 onward.
BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    method    TEXT NOT NULL,
    url       TEXT NOT NULL,
    headers   TEXT,
    params    TEXT,
    body      TEXT,
    body_type TEXT,
    auth_type TEXT,
    status    INTEGER,
    duration  REAL,
    curl_cmd  TEXT
);
"""

CURRENT_VERSION = 2


def open_connection(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the table if absent and apply incremental migrations.

    Uses ``PRAGMA user_version`` so columns added in later versions land on
    existing databases too (a plain ``CREATE TABLE IF NOT EXISTS`` never would).
    """
    conn.executescript(BASE_SCHEMA)
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 2:
        # v1 -> v2: full request snapshot for lossless replay.
        _add_column_if_missing(conn, "history", "config_json", "TEXT")

    if version < CURRENT_VERSION:
        conn.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
    conn.commit()


def secure_paths(db_path: str | Path) -> None:
    """chmod the app dir to 0700 and the DB file to 0600 (best effort).

    History holds request metadata that may include hostnames and (with
    --no-redact) credentials; it must not be world-readable. No-ops on
    platforms without POSIX permissions.
    """
    path = Path(db_path)
    if str(path) == ":memory:":
        return
    try:
        if path.parent.exists():
            os.chmod(path.parent, 0o700)
        if path.exists():
            os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass
