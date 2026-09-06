"""G.1 tests: payload source manager (offline, using a local git remote)."""

import shutil
import subprocess

import pytest

from curlcommander.core import payload_sources as ps


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def local_remote(tmp_path):
    """A tiny local git repo standing in for SecLists (no network)."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _git(["init", "-q"], remote)
    _git(["config", "user.email", "t@t"], remote)
    _git(["config", "user.name", "t"], remote)
    (remote / "Discovery").mkdir()
    (remote / "Discovery" / "common.txt").write_text("admin\nlogin\n")
    _git(["add", "-A"], remote)
    _git(["commit", "-q", "-m", "init"], remote)
    return remote


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_PAYLOADS", str(tmp_path / "data"))
    monkeypatch.delenv("SECLISTS_PATH", raising=False)


def test_builtin_sources_present():
    sources = ps.load_sources()
    assert {"seclists", "payloadsallthethings", "fuzzdb"} <= set(sources)
    assert sources["seclists"].repo.endswith("SecLists.git")


@pytest.mark.skipif(not shutil.which("git"), reason="git required")
def test_sync_clones_and_update_pulls(monkeypatch, local_remote, tmp_path):
    # Point the seclists source at the local remote.
    monkeypatch.setattr(
        ps,
        "load_sources",
        lambda: {"seclists": ps.Source("seclists", str(local_remote), "seclists", [])},
    )
    dest = ps.sync("seclists")
    assert (dest / "Discovery" / "common.txt").exists()
    assert ps.is_available("seclists")

    # A new commit upstream, then update() fast-forwards.
    (local_remote / "Discovery" / "extra.txt").write_text("x\n")
    _git(["add", "-A"], local_remote)
    _git(["commit", "-q", "-m", "more"], local_remote)
    ps.update("seclists")
    assert (dest / "Discovery" / "extra.txt").exists()


def test_seclists_path_override_not_touched(monkeypatch, tmp_path):
    external = tmp_path / "my-seclists"
    (external / "Discovery").mkdir(parents=True)
    (external / "Discovery" / "common.txt").write_text("a\n")
    monkeypatch.setenv("SECLISTS_PATH", str(external))

    assert ps.source_dir("seclists") == external
    assert ps.is_available("seclists")
    # sync must return the external dir without cloning over it.
    assert ps.sync("seclists") == external


def test_add_custom_source(tmp_path):
    ps.add_custom_source("mylists", "/opt/mylists")
    sources = ps.load_sources()
    assert "mylists" in sources
    assert sources["mylists"].repo == "/opt/mylists"


def test_unknown_source_raises():
    with pytest.raises(ps.PayloadSourceError):
        ps.sync("does-not-exist")


def test_freshness_marker_and_stale(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    d = tmp_path / "src"
    d.mkdir()
    (d / "wordlist.txt").write_text("a\n", encoding="utf-8")
    monkeypatch.setattr(ps, "source_dir", lambda name: d)
    monkeypatch.setattr(ps, "load_sources", lambda: {"s": ps.Source("s", "", "s", [])})

    # A fresh sentinel: not stale.
    ps._mark_synced(d)
    assert ps.last_sync_time("s") is not None
    assert ps.is_stale("s") is False
    assert ps.stale_sources() == []

    # An old sentinel: stale, and listed by stale_sources().
    old = (datetime.now() - timedelta(days=ps.STALE_AFTER_DAYS + 10)).isoformat(timespec="seconds")
    (d / ps.SYNC_MARKER).write_text(old, encoding="utf-8")
    assert ps.is_stale("s") is True
    assert ps.stale_sources() == ["s"]


def test_warn_stale_payloads_helper(monkeypatch):
    from curlcommander.cli import runner

    monkeypatch.setattr(runner.payload_sources, "stale_sources", lambda: ["seclists"])
    runner._warn_stale_payloads()  # must not raise; prints a one-line notice
    monkeypatch.setattr(runner.payload_sources, "stale_sources", lambda: [])
    runner._warn_stale_payloads()
