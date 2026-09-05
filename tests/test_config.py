"""F1.2 tests: platform config dir, env override, legacy migration."""

import importlib

import curlcommander.config as config


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path / "portable"))
    assert config.app_dir() == tmp_path / "portable"


def test_app_dir_is_platform_specific(monkeypatch):
    monkeypatch.delenv("CURLCOMMANDER_HOME", raising=False)
    # Whatever the platform, it is an absolute path under the user profile.
    assert config.app_dir().is_absolute()


def test_migrate_legacy_moves_history(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy" / ".curlcommander"
    legacy.mkdir(parents=True)
    (legacy / "history.db").write_bytes(b"OLDDB")
    (legacy / "sessions").mkdir()
    dest = tmp_path / "new" / "curlcommander"

    monkeypatch.setattr(config, "LEGACY_DIR", legacy)
    result = config.migrate_legacy(target=dest)

    assert result == dest
    assert (dest / "history.db").read_bytes() == b"OLDDB"
    assert (dest / "sessions").is_dir()


def test_migrate_is_noop_when_target_has_db(monkeypatch, tmp_path):
    legacy = tmp_path / ".curlcommander"
    legacy.mkdir()
    (legacy / "history.db").write_bytes(b"OLD")
    dest = tmp_path / "new"
    dest.mkdir()
    (dest / "history.db").write_bytes(b"KEEP")

    monkeypatch.setattr(config, "LEGACY_DIR", legacy)
    assert config.migrate_legacy(target=dest) is None
    assert (dest / "history.db").read_bytes() == b"KEEP"  # not overwritten


def test_migrate_is_noop_without_legacy(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LEGACY_DIR", tmp_path / "does-not-exist")
    assert config.migrate_legacy(target=tmp_path / "new") is None


def test_reload_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path / "h"))
    importlib.reload(config)
    try:
        assert config.APP_DIR == tmp_path / "h"
        assert config.DB_PATH == tmp_path / "h" / "history.db"
    finally:
        monkeypatch.delenv("CURLCOMMANDER_HOME", raising=False)
        importlib.reload(config)


def test_export_json_uses_lf_newlines(tmp_path):
    from curlcommander.core.request_model import HistoryEntry, RequestConfig
    from curlcommander.storage.history_repo import HistoryRepo

    repo = HistoryRepo(db_path=":memory:")
    repo.save(
        HistoryEntry(
            id=0,
            timestamp="t",
            request=RequestConfig(method="GET", url="https://x"),
            status_code=200,
            duration_ms=1.0,
            curl_cmd="",
        )
    )
    out = tmp_path / "h.json"
    repo.export_json(out)
    repo.close()
    assert b"\r\n" not in out.read_bytes()  # LF only, reproducible across OSes
    assert b"\n" in out.read_bytes()
