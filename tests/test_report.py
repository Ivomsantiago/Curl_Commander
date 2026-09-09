"""Tests for the engagement report + ValidationResult persistence (item 6)."""

import types

from curlcommander.cli import runner
from curlcommander.config import db_path_for
from curlcommander.core.report import build_report, report_severity
from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.core.validators.base import CANDIDATE, CONFIRMED, NOT_VULNERABLE, ValidationResult
from curlcommander.storage.history_repo import HistoryRepo
from curlcommander.storage.validation_repo import StoredValidation, ValidationRepo


def _stored(result: ValidationResult, id: int = 1) -> StoredValidation:
    return StoredValidation(id=id, timestamp="2026-09-07T00:00:00", engagement="ENG", result=result)


# --- severity mapping -----------------------------------------------------


def test_report_severity_uses_discovery_then_extras():
    assert report_severity("xss") == "medium"  # from discovery._SEVERITY
    assert report_severity("ssrf") == "medium"
    assert report_severity("idor") == "high"  # merged into the same shared table
    assert report_severity("clickjacking") == "low"
    assert report_severity("unknown") == "low"


def test_report_severity_evidence_override_wins():
    # A validator can flag its own instance as weaker/stronger than the
    # category default (e.g. SSRF DNS-only vs. a full HTTP connection).
    assert report_severity("ssrf", {"severity": "high"}) == "high"
    assert report_severity("ssrf", {"severity": "medium"}) == "medium"
    assert report_severity("ssrf", {"severity": "not-a-real-severity"}) == "medium"  # ignored, falls back
    assert report_severity("ssrf", None) == "medium"


# --- persistence roundtrip + migration ------------------------------------


def test_validation_repo_roundtrip(tmp_path):
    db = tmp_path / "h.db"
    repo = ValidationRepo(str(db))
    try:
        assert repo._conn.execute("PRAGMA user_version").fetchone()[0] == 6
        repo.save(
            "ENG",
            ValidationResult("ssrf", CONFIRMED, "https://t/fetch", detail="callback hit", evidence={"proto": "http"}),
            "2026-09-07T00:00:00",
        )
        repo.save("OTHER", ValidationResult("xss", CONFIRMED, "https://t/x"), "2026-09-07T00:00:01")
        eng = repo.load("ENG")
        assert len(eng) == 1
        assert eng[0].result.category == "ssrf"
        assert eng[0].result.evidence == {"proto": "http"}
        assert repo.engagements() == ["ENG", "OTHER"]
    finally:
        repo.close()


# --- HTML rendering -------------------------------------------------------


def test_build_report_groups_and_redacts():
    stored = [
        _stored(ValidationResult("idor", CONFIRMED, "https://api/orders/101", detail="B viu recurso de A"), 1),
        _stored(
            ValidationResult("xss", CONFIRMED, "https://t/s?q=x", detail="script executou", payload="<svg onload=1>"), 2
        ),
    ]
    doc = build_report("ENG", stored)
    assert "<!doctype html>" in doc
    assert "Severidade Alta (1)" in doc  # idor -> high
    assert "Severidade Média (1)" in doc  # xss -> medium
    # payload is HTML-escaped, never raw markup that could execute in a browser
    assert "<svg onload=1>" not in doc
    assert "&lt;svg onload=1&gt;" in doc
    # repro curl + remediation present
    assert "curl" in doc
    assert "Remediação" in doc


def test_build_report_renders_evidence_list():
    stored = [
        _stored(
            ValidationResult(
                "idor", CONFIRMED, "https://api/o/1", detail="d", evidence={"status_a": 200, "status_b": 200}
            )
        )
    ]
    doc = build_report("ENG", stored)
    assert "Evidência" in doc
    assert "status_a" in doc and "status_b" in doc


def test_validation_repo_context_manager_and_bad_evidence(tmp_path):
    db = tmp_path / "h.db"
    with ValidationRepo(str(db)) as repo:  # __enter__/__exit__
        repo.save("ENG", ValidationResult("xss", CONFIRMED, "https://t/x"), "2026-09-07T00:00:00")
        # Corrupt the evidence JSON directly; the loader must degrade to {}.
        repo._conn.execute("UPDATE validation_results SET evidence = ? WHERE id = 1", ("not json",))
        repo._conn.commit()
        assert repo.load("ENG")[0].result.evidence == {}


def test_build_report_secret_in_url_is_redacted():
    stored = [_stored(ValidationResult("ssrf", CONFIRMED, "https://t/f?token=SUPERSECRET&x=1"))]
    doc = build_report("ENG", stored)
    assert "SUPERSECRET" not in doc  # query secret redacted before entering HTML


def test_build_report_no_confirmed_shows_empty_and_others():
    stored = [_stored(ValidationResult("xss", NOT_VULNERABLE, "https://t/x", detail="nada refletiu"))]
    doc = build_report("ENG", stored)
    assert "Nenhum achado confirmado" in doc
    assert "Não conclusivos" in doc
    assert "nada refletiu" in doc


# --- CLI dispatch ---------------------------------------------------------


def test_run_report_writes_html(tmp_path, monkeypatch, capsys):
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", str(db))
    # --engagement uses its own isolated DB (8.1), not the ad-hoc DB_PATH.
    iso_db = db_path_for("ENG", db)
    repo = ValidationRepo(str(iso_db))
    repo.save("ENG", ValidationResult("ssrf", CONFIRMED, "https://t/f", detail="hit"), "2026-09-07T00:00:00")
    repo.close()

    out = tmp_path / "report.html"
    code = runner._run_report(types.SimpleNamespace(engagement="ENG", out=str(out)))
    assert code == runner.EXIT_OK
    assert out.exists()
    assert "<!doctype html>" in out.read_text(encoding="utf-8")
    assert "Relatório gravado em" in capsys.readouterr().out


def test_run_report_no_findings_is_usage(tmp_path, monkeypatch, capsys):
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", str(db))
    ValidationRepo(str(db)).close()  # create empty DB
    code = runner._run_report(types.SimpleNamespace(engagement="NONE", out=str(tmp_path / "r.html")))
    assert code == runner.EXIT_USAGE
    assert "Nenhum achado" in capsys.readouterr().out


# --- evidence redaction at persistence time --------------------------------


def test_persist_validation_redacts_evidence_before_saving(tmp_path, monkeypatch):
    """Evidence can carry a captured raw request/DOM with real credentials in
    it — it must never reach disk unredacted, matching how request history is
    already redacted by default."""
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", str(db))
    result = ValidationResult(
        "ssrf",
        CONFIRMED,
        "https://t/fetch",
        detail="callback hit",
        evidence={
            "raw_request": "GET / HTTP/1.1\r\nHost: t\r\nCookie: session=SUPERSECRET\r\nAuthorization: Bearer tok123\r\n\r\n",
            "chain": ["https://t/r?token=leak-me"],
        },
    )
    runner._persist_validation("ENG", result)

    repo = ValidationRepo(str(db_path_for("ENG", db)))
    try:
        stored = repo.load("ENG")
    finally:
        repo.close()
    assert len(stored) == 1
    ev = stored[0].result.evidence
    assert "SUPERSECRET" not in ev["raw_request"]
    assert "tok123" not in ev["raw_request"]
    assert "Cookie:" in ev["raw_request"]  # header name kept, value masked
    assert "leak-me" not in ev["chain"][0]


# --- history + bounty-scan candidates in the aggregated report ------------


def test_build_report_includes_history_appendix():
    entry = HistoryEntry(
        id=1,
        timestamp="2026-09-07T00:00:00",
        request=RequestConfig(method="GET", url="https://api.t/x?token=SECRET"),
        status_code=200,
        duration_ms=12.0,
        curl_cmd="curl https://api.t/x",
        engagement="ENG",
    )
    doc = build_report("ENG", [], [entry])
    assert "Requisições do engajamento (1)" in doc
    assert "api.t/x" in doc
    assert "SECRET" not in doc  # query secret redacted in the appendix too


def test_run_report_aggregates_history_alongside_findings(tmp_path, monkeypatch):
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", str(db))
    iso_db = db_path_for("ENG", db)

    vrepo = ValidationRepo(str(iso_db))
    vrepo.save("ENG", ValidationResult("xss", CONFIRMED, "https://t/x"), "2026-09-07T00:00:00")
    vrepo.close()

    hrepo = HistoryRepo(str(iso_db))
    hrepo.save(
        HistoryEntry(
            id=0,
            timestamp="2026-09-07T00:00:01",
            request=RequestConfig(method="GET", url="https://t/probe"),
            status_code=200,
            duration_ms=5.0,
            curl_cmd="curl https://t/probe",
            engagement="ENG",
        )
    )
    hrepo.close()

    out = tmp_path / "report.html"
    code = runner._run_report(types.SimpleNamespace(engagement="ENG", out=str(out)))
    assert code == runner.EXIT_OK
    doc = out.read_text(encoding="utf-8")
    assert "t/probe" in doc
    assert "Requisições do engajamento (1)" in doc


def test_bounty_scan_candidates_persist_and_appear_in_report(tmp_path, monkeypatch):
    """bounty-scan candidates are never confirmations — they persist with
    verdict CANDIDATE and land in the report's non-conclusive section, never
    the confirmed/severity buckets."""
    db = tmp_path / "h.db"
    monkeypatch.setattr(runner, "DB_PATH", str(db))
    result = ValidationResult(
        "ssti", CANDIDATE, "https://t/x?q=%7B%7B7*7%7D%7D", detail="anomalous response vs baseline", payload="{{7*7}}"
    )
    runner._persist_validation("ENG", result)

    repo = ValidationRepo(str(db_path_for("ENG", db)))
    try:
        stored = repo.load("ENG")
    finally:
        repo.close()
    assert stored[0].result.verdict == CANDIDATE

    doc = build_report("ENG", stored)
    assert "Nenhum achado confirmado" in doc  # CANDIDATE never counts as CONFIRMED
    assert "Não conclusivos" in doc
    assert "CANDIDATE" in doc
