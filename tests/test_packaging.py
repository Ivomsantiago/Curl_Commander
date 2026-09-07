"""Packaging metadata: both binary names must be wired to the same entry point."""

import tomllib
from pathlib import Path


def _project_scripts() -> dict[str, str]:
    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["scripts"]


def test_curlcmd_entry_point_unchanged():
    assert _project_scripts()["curlcmd"] == "curlcommander.main:main"


def test_curlcommander_alias_entry_point():
    scripts = _project_scripts()
    assert scripts["curlcommander"] == "curlcommander.main:main"
    assert scripts["curlcommander"] == scripts["curlcmd"]
