"""Tests for the engagement report + ValidationResult persistence (item 6)."""

import types

from curlcommander.cli import runner
from curlcommander.core.report import build_report, report_severity
from curlcommander.core.validators.base import CONFIRMED, NOT_VULNERABLE, ValidationResult
from curlcommander.storage.validation_repo import StoredValidation, ValidationRepo


def _stored(result: ValidationResult, id: int = 1) -> StoredValidation:
    return StoredValidation(id=id, timestamp="2026-09-07T00:00:00", engagement="ENG", result=result)


# --- severity mapping -----------------------------------------------------


def test_report_severity_uses_discovery_then_extras():
    assert report_severity("xss") == "medium"  # from discovery._SEVERITY
    assert report_severity("ssrf") == "medium"
    assert report_severity("idor") == "high"  # extra map
    assert report_severity("clickjacking") == "low"
    assert report_severity("unknown") == "low"


# --- persistence roundtrip + migration ------------------------------------


def test_validation_repo_roundtrip(tmp_path):
    db = tmp_path / "h.db"
    repo = ValidationRepo(str(db))
    try:
        assert repo._conn.execute("PRAGMA user_version").fetchone()[0] == 4
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
    repo = ValidationRepo(str(db))
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
