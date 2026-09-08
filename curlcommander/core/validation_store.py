"""Persist a validated finding for `curlcmd report` to later aggregate.

Extracted out of ``cli/runner.py`` so both the CLI's ``validate``/`bounty-scan`
commands and the GUI's Validate tab (item 9) share one persistence path —
in particular the redaction step, which must never drift between the two
callers: a validator's evidence can carry a captured raw request or DOM
snapshot with real credentials in it.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path

from curlcommander.config import DB_PATH, db_path_for
from curlcommander.core.redaction import redact_evidence
from curlcommander.core.validators.base import ValidationResult
from curlcommander.storage.validation_repo import ValidationRepo


def persist_validation(engagement: str | None, result: ValidationResult, default_db: str | Path = DB_PATH) -> None:
    """No-op without an --engagement — findings are only durable per engagement.

    ``default_db`` is the ad-hoc (no-engagement) DB path this engagement's
    isolated DB is resolved next to (see config.db_path_for) — callers that
    track their own default (e.g. the CLI's module-level ``DB_PATH``, which
    tests monkeypatch) should pass it explicitly rather than relying on the
    import-time default here.
    """
    if not engagement:
        return
    redacted = dataclasses.replace(result, evidence=redact_evidence(result.evidence))
    repo = ValidationRepo(db_path_for(engagement, default_db))
    try:
        repo.save(engagement, redacted, datetime.now().isoformat(timespec="seconds"))
    finally:
        repo.close()
