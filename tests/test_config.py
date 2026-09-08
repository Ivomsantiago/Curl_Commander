"""F1.2 tests: platform config dir, env override, legacy migration."""

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


def test_reload_respects_override(tmp_path):
    """A fresh process with CURLCOMMANDER_HOME set computes APP_DIR/DB_PATH
    from it. Checked via a real subprocess rather than importlib.reload():
    reload() mutates the shared module dict *in place*, so every class/
    function defined in config.py gets a brand-new identity that no longer
    matches whatever any other already-imported module captured via
    `from curlcommander.config import X` before the reload — including
    curlcommander.cli.runner's own `except InvalidEngagementName` — a subtle,
    session-wide test-isolation trap a plain try/finally restore cannot fix
    (it restores the *values* correctly, never the *identities*)."""
    import json
    import os
    import subprocess
    import sys

    target = tmp_path / "h"
    env = dict(os.environ, CURLCOMMANDER_HOME=str(target))
    code = "import json, curlcommander.config as c; print(json.dumps({'app_dir': str(c.APP_DIR), 'db_path': str(c.DB_PATH)}))"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert data["app_dir"] == str(target)
    assert data["db_path"] == str(target / "history.db")


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
