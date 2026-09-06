"""Manage external payload sources (SecLists, PayloadsAllTheThings, FuzzDB).

SecLists alone is ~1 GB, so nothing is vendored. `sync` shallow-clones sources
into the OS data dir (sparse-checkout of the used subtrees when git supports
it); env overrides point at an existing checkout instead. All git work goes
through subprocess with argument lists --- never a shell string.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from curlcommander.config import app_dir

# A source not refreshed within this window is flagged as stale (0.3).
STALE_AFTER_DAYS = 30
# Sentinel file written on each successful sync to record when it happened.
SYNC_MARKER = ".curlcmd_synced"


class PayloadSourceError(RuntimeError):
    pass


@dataclass
class Source:
    name: str
    repo: str
    dir: str
    sparse: list[str]


def _builtin_sources() -> dict[str, Any]:
    text = resources.files("curlcommander.data").joinpath("sources.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def payloads_root() -> Path:
    """Directory holding synced sources (or an override)."""
    override = os.environ.get("CURLCOMMANDER_PAYLOADS")
    if override:
        return Path(override)
    return app_dir() / "payloads"


def _user_sources_file() -> Path:
    return payloads_root() / "sources.yaml"


def load_sources() -> dict[str, Source]:
    """Built-in sources merged with any user-defined ones in the data dir."""
    merged: dict[str, Any] = dict(_builtin_sources().get("sources", {}))
    user_file = _user_sources_file()
    if user_file.exists():
        try:
            user = yaml.safe_load(user_file.read_text(encoding="utf-8")) or {}
            merged.update(user.get("sources", {}))
        except (yaml.YAMLError, OSError):
            pass
    out: dict[str, Source] = {}
    for name, cfg in merged.items():
        out[name] = Source(
            name=name,
            repo=str(cfg.get("repo", "")),
            dir=str(cfg.get("dir", name)),
            sparse=list(cfg.get("sparse", []) or []),
        )
    return out


def add_custom_source(name: str, url_or_path: str) -> None:
    """Register a custom source (git URL or local path) in the user sources.yaml."""
    root = payloads_root()
    root.mkdir(parents=True, exist_ok=True)
    user_file = _user_sources_file()
    data: dict[str, Any] = {"sources": {}}
    if user_file.exists():
        data = yaml.safe_load(user_file.read_text(encoding="utf-8")) or {"sources": {}}
    data.setdefault("sources", {})[name] = {"repo": url_or_path, "dir": name, "sparse": []}
    user_file.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8", newline="\n")


def source_dir(name: str) -> Path:
    """Where a source lives on disk, honouring env overrides.

    SECLISTS_PATH points directly at a SecLists checkout; a local-path custom
    source resolves to that path; everything else lives under payloads_root().
    """
    if name == "seclists":
        env = os.environ.get("SECLISTS_PATH")
        if env:
            return Path(env)
    sources = load_sources()
    src = sources.get(name)
    if src and src.repo and "://" not in src.repo and not src.repo.endswith(".git"):
        candidate = Path(src.repo)
        if candidate.exists():
            return candidate
    return payloads_root() / (src.dir if src else name)


def is_available(name: str) -> bool:
    d = source_dir(name)
    return d.is_dir() and any(d.iterdir())


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    if not shutil.which("git"):
        raise PayloadSourceError("git is required to sync payload sources but was not found on PATH")
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PayloadSourceError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from exc


def sync(name: str, depth: int = 1) -> Path:
    """Shallow-clone (or update) a source. Returns its directory.

    No-op with a message when the source is provided via an env override.
    """
    sources = load_sources()
    if name not in sources:
        raise PayloadSourceError(f"unknown source: {name} (known: {', '.join(sorted(sources))})")

    dest = source_dir(name)
    root = payloads_root()
    is_managed = dest.parent == root or root in dest.parents
    if not is_managed:
        # An external/override checkout (SECLISTS_PATH, local custom source):
        # never touch it.
        return dest

    src = sources[name]
    if (dest / ".git").exists():
        _git(["pull", "--ff-only", "--depth", str(depth)], cwd=dest)
        _mark_synced(dest)
        return dest

    dest.mkdir(parents=True, exist_ok=True)
    if src.sparse and _supports_sparse():
        _git(["clone", "--depth", str(depth), "--filter=blob:none", "--sparse", src.repo, str(dest)])
        _git(["sparse-checkout", "set", *src.sparse], cwd=dest)
    else:
        # Remove the empty dir so clone can create it.
        if dest.exists() and not any(dest.iterdir()):
            dest.rmdir()
        _git(["clone", "--depth", str(depth), src.repo, str(dest)])
    _mark_synced(dest)
    return dest


def _mark_synced(dest: Path) -> None:
    """Record the sync time in a sentinel file (best-effort)."""
    try:
        (dest / SYNC_MARKER).write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8", newline="\n")
    except OSError:
        pass


def last_sync_time(name: str) -> datetime | None:
    """Best-effort timestamp of the last sync for a source, or None if unknown.

    Prefers the sentinel written by :func:`sync`; falls back to git's
    ``FETCH_HEAD`` mtime, then the source directory's own mtime. Returns None
    when the source is not present on disk at all.
    """
    dest = source_dir(name)
    if not (dest.is_dir() and any(dest.iterdir())):
        return None
    marker = dest / SYNC_MARKER
    if marker.exists():
        try:
            return datetime.fromisoformat(marker.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass
    fetch_head = dest / ".git" / "FETCH_HEAD"
    probe = fetch_head if fetch_head.exists() else dest
    try:
        return datetime.fromtimestamp(probe.stat().st_mtime)
    except OSError:
        return None


def is_stale(name: str, max_age_days: int = STALE_AFTER_DAYS) -> bool:
    """True when a source is present but hasn't been refreshed recently."""
    ts = last_sync_time(name)
    if ts is None:
        return False
    return datetime.now() - ts > timedelta(days=max_age_days)


def stale_sources(max_age_days: int = STALE_AFTER_DAYS) -> list[str]:
    """Names of synced sources older than the freshness window."""
    return [n for n in load_sources() if is_available(n) and is_stale(n, max_age_days)]


def update(name: str | None = None) -> list[Path]:
    """Update one source, or every available one."""
    names = [name] if name else [n for n in load_sources() if is_available(n)]
    return [sync(n) for n in names]


def _supports_sparse() -> bool:
    try:
        out = _git(["--version"]).stdout
    except PayloadSourceError:
        return False
    # sparse-checkout landed in git 2.25.
    parts = out.strip().split()
    for token in parts:
        if token[0].isdigit():
            major, _, minor = token.partition(".")
            try:
                return (int(major), int(minor.split(".")[0] or 0)) >= (2, 25)
            except ValueError:
                return False
    return False
