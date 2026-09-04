"""Cookie jar persistence for session-based flows.

Stored as JSON (name/value/domain/path) rather than the Netscape format so it
is trivial to inspect. httpx.Cookies drives the actual send/receive so
Set-Cookie updates round-trip correctly across requests under one --session.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from curlcommander.config import APP_DIR


def session_jar_path(name: str) -> Path:
    return APP_DIR / "sessions" / f"{name}.cookies.json"


def load_jar(path: str | Path) -> httpx.Cookies:
    cookies = httpx.Cookies()
    p = Path(path)
    if not p.exists():
        return cookies
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cookies
    for c in data:
        cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    return cookies


def save_jar(path: str | Path, cookies: httpx.Cookies) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = [
        {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
        for c in cookies.jar
    ]
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    try:
        p.chmod(0o600)  # cookies are session credentials
    except OSError:
        pass
