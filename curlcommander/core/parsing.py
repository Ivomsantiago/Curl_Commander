"""Single source of truth for parsing ``Key: Value`` / ``key=value`` input.

Previously three call sites (CLI runner, wizard, GUI) each required a literal
``": "`` separator, so ``-H "Accept:application/json"`` (no space) silently
produced no header at all. Parsing now splits on the first delimiter and
strips, and reports genuinely malformed input instead of dropping it.
"""

from __future__ import annotations

from curlcommander.core.headers import HeaderList


class ParseError(ValueError):
    """Raised for input that cannot be parsed as a header or param."""


def parse_header(line: str) -> tuple[str, str]:
    """Parse a single ``Key: Value`` header line (split on first colon)."""
    if ":" not in line:
        raise ParseError(f"invalid header (expected 'Key: Value'): {line!r}")
    key, value = line.split(":", 1)
    key = key.strip()
    if not key:
        raise ParseError(f"invalid header (empty name): {line!r}")
    return key, value.strip()


def parse_param(line: str) -> tuple[str, str]:
    """Parse a single ``key=value`` query-param line (split on first '=')."""
    if "=" not in line:
        raise ParseError(f"invalid param (expected 'key=value'): {line!r}")
    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        raise ParseError(f"invalid param (empty name): {line!r}")
    return key, value.strip()


def parse_headers(lines: list[str]) -> HeaderList:
    """Parse many header lines, skipping blank ones. Raises on malformed."""
    result = HeaderList()
    for line in lines:
        if not line.strip():
            continue
        k, v = parse_header(line)
        result.append(k, v)
    return result


def parse_params(lines: list[str]) -> HeaderList:
    """Parse many param lines, skipping blank ones. Raises on malformed."""
    result = HeaderList()
    for line in lines:
        if not line.strip():
            continue
        k, v = parse_param(line)
        result.append(k, v)
    return result
