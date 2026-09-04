"""Built-in payload library (2B.4 scaffold).

Payloads live in ``curlcommander/data/payloads/<name>.txt`` (one per line) so the
set is data, not code, and easy to extend. ``--payloads sqli`` seeds a fuzz
wordlist; the same lists feed the assisted-testing heuristics later.
"""

from __future__ import annotations

from importlib import resources


def available() -> list[str]:
    names = []
    for entry in resources.files("curlcommander.data.payloads").iterdir():
        if entry.name.endswith(".txt"):
            names.append(entry.name[:-4])
    return sorted(names)


def load(name: str) -> list[str]:
    """Load a built-in payload set by name. Raises KeyError if unknown."""
    if name not in available():
        raise KeyError(f"unknown payload set: {name} (available: {', '.join(available())})")
    text = resources.files("curlcommander.data.payloads").joinpath(f"{name}.txt").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def reflects(payload: str, response_body: str) -> bool:
    """Heuristic: did the payload (or its core) reflect unescaped in the body?

    Only flags a candidate to investigate --- it never asserts exploitation.
    """
    return bool(payload) and payload in response_body
