"""Regression tests for schema migration (3.6) and DB permissions (1.5)."""

import os
import sqlite3
import sys

import pytest

from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.storage.db import BASE_SCHEMA, init_schema, open_connection
from curlcommander.storage.history_repo import HistoryRepo


def test_migration_adds_config_json_to_legacy_db(tmp_path):
    db = tmp_path / "legacy.db"
    # Simulate an old v1 database: base table, user_version 0, no config_json.
    conn = sqlite3.connect(db)
    conn.executescript(BASE_SCHEMA)
    conn.execute(
        "INSERT INTO history (ts, method, url, headers, params, body, body_type, auth_type, status, duration, curl_cmd)"
        " VALUES ('t','GET','https://old','[]','[]','','none','none',200,1.0,'curl https://old')"
    )
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(history)")}
    assert "config_json" not in cols
    conn.close()

    # Opening through the repo runs the migration.
    repo = HistoryRepo(db_path=str(db))
    cols = {r[1] for r in repo._conn.execute("PRAGMA table_info(history)")}
    assert "config_json" in cols
    assert repo._conn.execute("PRAGMA user_version").fetchone()[0] == 2

    # Legacy row (config_json NULL) still reads back via the flat columns.
    entry = repo.get_by_id(1)
    assert entry is not None
    assert entry.request.url == "https://old"
    repo.close()


def test_migration_is_idempotent(tmp_path):
    db = tmp_path / "h.db"
    HistoryRepo(db_path=str(db)).close()
    repo = HistoryRepo(db_path=str(db))  # second open must not error
    assert repo._conn.execute("PRAGMA user_version").fetchone()[0] == 2
    repo.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_db_and_dir_permissions(tmp_path):
    appdir = tmp_path / "app"
    db = appdir / "history.db"
    repo = HistoryRepo(db_path=str(db))
    entry = HistoryEntry(
        id=0, timestamp="t", request=RequestConfig(method="GET", url="https://x"),
        status_code=200, duration_ms=1.0, curl_cmd="",
    )
    repo.save(entry)
    repo.close()
    assert (os.stat(db).st_mode & 0o777) == 0o600
    assert (os.stat(appdir).st_mode & 0o777) == 0o700
