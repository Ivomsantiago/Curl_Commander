"""Pluggable payload encoders for bypass testing (2B.3).

A simple name -> callable registry so payloads (and later payload libraries in
2B.4) can be transformed and chained: ``--encode url,base64`` applies url then
base64. New encoders register with @encoder without touching call sites.
"""

from __future__ import annotations

import base64 as _b64
from collections.abc import Callable
from urllib.parse import quote

Encoder = Callable[[str], str]
_REGISTRY: dict[str, Encoder] = {}


def encoder(name: str) -> Callable[[Encoder], Encoder]:
    def register(fn: Encoder) -> Encoder:
        _REGISTRY[name] = fn
        return fn

    return register


@encoder("url")
def _url(value: str) -> str:
    return quote(value, safe="")


@encoder("double-url")
def _double_url(value: str) -> str:
    return quote(quote(value, safe=""), safe="")


@encoder("base64")
def _base64(value: str) -> str:
    return _b64.b64encode(value.encode()).decode()


@encoder("hex")
def _hex(value: str) -> str:
    return value.encode().hex()


@encoder("html-entity")
def _html_entity(value: str) -> str:
    return "".join(f"&#{ord(c)};" for c in value)


@encoder("unicode")
def _unicode(value: str) -> str:
    return "".join(f"\\u{ord(c):04x}" for c in value)


def available() -> list[str]:
    return sorted(_REGISTRY)


def apply_encoders(value: str, names: list[str]) -> str:
    """Apply a chain of encoders left to right. Unknown names raise KeyError."""
    for name in names:
        name = name.strip()
        if not name:
            continue
        if name not in _REGISTRY:
            raise KeyError(f"unknown encoder: {name} (available: {', '.join(available())})")
        value = _REGISTRY[name](value)
    return value
