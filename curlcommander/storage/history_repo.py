import json
import sqlite3
from pathlib import Path

from curlcommander.config import DB_PATH, HISTORY_LIMIT
from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.storage.db import init_schema, open_connection


class HistoryRepo:
    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        is_memory = str(db_path) == ":memory:"
        if not is_memory:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = open_connection(db_path)
        init_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "HistoryRepo":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(self, entry: HistoryEntry) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO history
                (ts, method, url, headers, params, body, body_type, auth_type, status, duration, curl_cmd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp,
                entry.request.method,
                entry.request.url,
                json.dumps(entry.request.headers.to_jsonable()),
                json.dumps(entry.request.params.to_jsonable()),
                entry.request.body,
                entry.request.body_type,
                entry.request.auth_type,
                entry.status_code,
                entry.duration_ms,
                entry.curl_cmd,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def load(self, limit: int = HISTORY_LIMIT) -> list[HistoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_by_id(self, id: int) -> HistoryEntry | None:
        row = self._conn.execute(
            "SELECT * FROM history WHERE id = ?", (id,)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def delete_by_id(self, id: int) -> None:
        self._conn.execute("DELETE FROM history WHERE id = ?", (id,))
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM history")
        self._conn.commit()

    def export_json(self, output_path: str | Path) -> None:
        rows = self._conn.execute("SELECT * FROM history ORDER BY id DESC").fetchall()
        entries = [self._entry_to_jsonable(self._row_to_entry(row)) for row in rows]
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    @staticmethod
    def _entry_to_jsonable(entry: HistoryEntry) -> dict:
        return {
            "id": entry.id,
            "timestamp": entry.timestamp,
            "request": entry.request.to_dict(),
            "status_code": entry.status_code,
            "duration_ms": entry.duration_ms,
            "curl_cmd": entry.curl_cmd,
        }

    def _row_to_entry(self, row: sqlite3.Row) -> HistoryEntry:
        request = RequestConfig(
            method=row["method"],
            url=row["url"],
            headers=HeaderList.from_jsonable(json.loads(row["headers"] or "[]")),
            params=HeaderList.from_jsonable(json.loads(row["params"] or "[]")),
            body=row["body"] or "",
            body_type=row["body_type"] or "none",
            auth_type=row["auth_type"] or "none",
        )
        return HistoryEntry(
            id=row["id"],
            timestamp=row["ts"],
            request=request,
            status_code=row["status"],
            duration_ms=row["duration"] or 0.0,
            curl_cmd=row["curl_cmd"] or "",
        )
