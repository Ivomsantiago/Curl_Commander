"""Unified payload catalog over embedded lists and synced sources.

Resolves requests by intent (``--payloads xss``) or by source-relative path
(``-w seclists:Discovery/Web-Content/common.txt``) into concrete payload lines,
using the curated ``payload_map.yaml`` plus the sources managed by
``payload_sources``. Deduplicates while preserving order.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from curlcommander.core import payload_sources, payloads


class CatalogError(ValueError):
    pass


def _map() -> dict[str, Any]:
    text = resources.files("curlcommander.data").joinpath("payload_map.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    result: dict[str, Any] = data.get("categories", {}) or {}
    return result


def categories() -> list[str]:
    return sorted(_map())


def _dedup(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def _read_lines(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


def resolve_spec(spec: str) -> list[str]:
    """Resolve a -w spec: ``<source>:relpath``, an embedded name, or a file path."""
    if ":" in spec and not Path(spec).exists():
        source, _, relpath = spec.partition(":")
        base = payload_sources.source_dir(source)
        if not base.exists():
            raise CatalogError(f"source {source!r} is not synced (run: curlcmd payloads sync {source})")
        target = base / relpath
        if not target.exists():
            raise CatalogError(f"{spec}: not found under {base}")
        return _read_lines(target)

    path = Path(spec)
    if path.exists():
        return _read_lines(path)
    # Fall back to an embedded payload set by bare name.
    try:
        return payloads.load(spec)
    except KeyError as exc:
        raise CatalogError(str(exc)) from exc


def category_files(category: str, all_sources: bool = False) -> list[Path]:
    """Files backing a category. Without all_sources, stop at the first hit."""
    spec = _map().get(category)
    if spec is None:
        raise CatalogError(f"unknown category: {category} (known: {', '.join(categories())})")

    files: list[Path] = []
    # Embedded lists first (always available).
    for name in spec.get("builtin", []) or []:
        with resources.as_file(resources.files("curlcommander.data.payloads").joinpath(f"{name}.txt")) as p:
            if p.exists():
                files.append(Path(p))
    if files and not all_sources:
        return files

    for source, patterns in spec.items():
        if source == "builtin":
            continue
        base = payload_sources.source_dir(source)
        if not base.exists():
            continue
        for pattern in patterns or []:
            files.extend(sorted(base.glob(pattern)))
        if files and not all_sources:
            return files
    return files


def load_category(category: str, all_sources: bool = False) -> list[str]:
    lines: list[str] = []
    for f in category_files(category, all_sources=all_sources):
        lines.extend(_read_lines(f))
    return _dedup(lines)


def search(term: str) -> list[str]:
    """Search wordlist filenames across embedded + synced sources."""
    term = term.lower()
    hits: list[str] = []
    for name in payloads.available():
        if term in name:
            hits.append(f"builtin:{name}")
    for src in payload_sources.load_sources():
        base = payload_sources.source_dir(src)
        if not base.exists():
            continue
        for path in base.rglob("*.txt"):
            if term in path.name.lower():
                hits.append(f"{src}:{path.relative_to(base).as_posix()}")
                if len(hits) > 500:
                    return hits
    return hits
