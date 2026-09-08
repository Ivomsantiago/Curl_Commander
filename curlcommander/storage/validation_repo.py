"""Persistence for validated findings (item 6), keyed by engagement.

Kept separate from :class:`HistoryRepo` so the report can aggregate findings
without touching the request-history read path. Both share the same schema and
migration (``storage/db.py``); this repo owns the ``validation_results`` table.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from curlcommander.config import DB_PATH
from curlcommander.core.validators.base import ValidationResult
from curlcommander.storage.db import init_schema, open_connection, secure_paths


@dataclass
class StoredValidation:
    id: int
    timestamp: str
    engagement: str
    result: ValidationResult


class ValidationRepo:
    def __init__(self, db_path: str | Path = DB_PATH) -> None:
        is_memory = str(db_path) == ":memory:"
        if not is_memory:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = open_connection(db_path)
        init_schema(self._conn)
        if not is_memory:
            secure_paths(db_path)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ValidationRepo:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def save(self, engagement: str, result: ValidationResult, timestamp: str) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO validation_results
                (ts, engagement, category, verdict, url, detail, payload, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                engagement,
                result.category,
                result.verdict,
                result.url,
                result.detail,
                result.payload,
                json.dumps(result.evidence),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def load(self, engagement: str) -> list[StoredValidation]:
        rows = self._conn.execute(
            "SELECT * FROM validation_results WHERE engagement = ? ORDER BY id",
            (engagement,),
        ).fetchall()
        return [self._row(row) for row in rows]

    def engagements(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT engagement FROM validation_results ORDER BY engagement").fetchall()
        return [row["engagement"] for row in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM validation_results").fetchone()
        return int(row[0])

    @staticmethod
    def _row(row: sqlite3.Row) -> StoredValidation:
        try:
            evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        except (json.JSONDecodeError, TypeError):
            evidence = {}
        return StoredValidation(
            id=row["id"],
            timestamp=row["ts"],
            engagement=row["engagement"],
            result=ValidationResult(
                category=row["category"],
                verdict=row["verdict"],
                url=row["url"],
                detail=row["detail"] or "",
                payload=row["payload"] or "",
                evidence=evidence if isinstance(evidence, dict) else {},
            ),
        )
