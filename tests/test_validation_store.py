"""Tests for core.validation_store.persist_validation — the shared
redact-then-save path behind both `cli/runner.py::_persist_validation` and
the GUI's Validate tab (item 9)."""

from curlcommander.config import db_path_for
from curlcommander.core.validation_store import persist_validation
from curlcommander.core.validators.base import CONFIRMED, ValidationResult
from curlcommander.storage.validation_repo import ValidationRepo


def test_persist_validation_saves_under_the_engagement(tmp_path):
    db = tmp_path / "h.db"
    result = ValidationResult("xss", CONFIRMED, "https://t/x", detail="alert fired")
    persist_validation("ENG", result, db)

    repo = ValidationRepo(db_path_for("ENG", db))
    try:
        stored = repo.load("ENG")
    finally:
        repo.close()
    assert len(stored) == 1
    assert stored[0].result.verdict == CONFIRMED


def test_persist_validation_redacts_sensitive_evidence(tmp_path):
    db = tmp_path / "h.db"
    result = ValidationResult(
        "ssrf",
        CONFIRMED,
        "https://t/fetch",
        evidence={"raw_request": "GET / HTTP/1.1\r\nAuthorization: Bearer tok123\r\n\r\n"},
    )
    persist_validation("ENG", result, db)

    repo = ValidationRepo(db_path_for("ENG", db))
    try:
        stored = repo.load("ENG")
    finally:
        repo.close()
    assert "tok123" not in stored[0].result.evidence["raw_request"]


def test_persist_validation_without_engagement_is_a_noop(tmp_path):
    db = tmp_path / "h.db"
    persist_validation(None, ValidationResult("xss", CONFIRMED, "https://t/x"), db)
    persist_validation("", ValidationResult("xss", CONFIRMED, "https://t/x"), db)
    # Nothing was ever created — no isolated DB, no ad-hoc DB either.
    assert not db.exists()
    assert not (tmp_path / "engagements").exists()
