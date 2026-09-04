"""Engagement scope enforcement (2B.8).

A professional responsibility, not decoration: refuse to fire at a host outside
the authorised allowlist so a typo can't hit production or a third party. The
allowlist file holds one entry per line: an exact host, a ``*.wildcard`` suffix,
a bare IP, or a CIDR range. Blank lines and ``#`` comments are ignored.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlsplit


class ScopeError(RuntimeError):
    """Raised when a request target is outside the authorised scope."""


def load_scope(path: str | Path) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [s.strip() for s in lines if s.strip() and not s.strip().startswith("#")]


def _host_matches(host: str, entry: str) -> bool:
    host = host.lower().strip(".")
    entry = entry.lower().strip()

    if entry.startswith("*."):
        suffix = entry[1:]  # ".example.com"
        return host == entry[2:] or host.endswith(suffix)

    # CIDR / IP entry.
    try:
        network = ipaddress.ip_network(entry, strict=False)
        try:
            return ipaddress.ip_address(host) in network
        except ValueError:
            return False
    except ValueError:
        pass

    return host == entry


def host_in_scope(host: str, entries: list[str]) -> bool:
    return any(_host_matches(host, e) for e in entries)


def url_in_scope(url: str, entries: list[str]) -> bool:
    if "://" not in url:
        url = "https://" + url
    host = urlsplit(url).hostname or ""
    return host_in_scope(host, entries)


def enforce(url: str, entries: list[str]) -> None:
    if not url_in_scope(url, entries):
        host = urlsplit(url if "://" in url else "https://" + url).hostname or url
        raise ScopeError(f"target {host!r} is out of scope (not in the allowlist)")
