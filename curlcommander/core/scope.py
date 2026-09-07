"""Engagement scope enforcement (2B.8).

A professional responsibility, not decoration: refuse to fire at a host outside
the authorised allowlist so a typo can't hit production or a third party. The
allowlist file holds one entry per line: an exact host, a ``*.wildcard`` suffix,
a bare IP, or a CIDR range. Blank lines and ``#`` comments are ignored.

A line prefixed with ``!`` is a deny (exclusion) entry rather than an allow
entry — e.g. a wildcard like ``*.example.com`` can cover a whole subdomain
tree while one host is carved back out with ``!excluded.example.com``. Deny
always wins over allow, regardless of where either line sits in the file: a
host matching any deny entry is out of scope even if it also matches an allow
entry (wildcard or otherwise). ``load_scope`` keeps deny entries in the
returned list with their ``!`` prefix intact — every function here that reads
entries (``host_in_scope``, ``url_in_scope``, ``enforce``) splits them back
into allow/deny internally and checks deny first, so callers that only ever
built plain allowlists (no ``!`` lines) see no change in behaviour.
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


def _split_entries(entries: list[str]) -> tuple[list[str], list[str]]:
    """Separate raw scope-file entries into (allow_entries, deny_entries).

    Deny entries are the ones prefixed with ``!`` in the source file; the
    prefix is stripped here so the rest of the module only ever matches bare
    host patterns.
    """
    allow_entries: list[str] = []
    deny_entries: list[str] = []
    for entry in entries:
        e = entry.strip()
        if e.startswith("!"):
            e = e[1:].strip()
            if e:
                deny_entries.append(e)
        elif e:
            allow_entries.append(e)
    return allow_entries, deny_entries


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
    allow_entries, deny_entries = _split_entries(entries)
    if any(_host_matches(host, e) for e in deny_entries):
        return False
    return any(_host_matches(host, e) for e in allow_entries)


def url_in_scope(url: str, entries: list[str]) -> bool:
    if "://" not in url:
        url = "https://" + url
    host = urlsplit(url).hostname or ""
    return host_in_scope(host, entries)


def enforce(url: str, entries: list[str]) -> None:
    if not url_in_scope(url, entries):
        host = urlsplit(url if "://" in url else "https://" + url).hostname or url
        _allow_entries, deny_entries = _split_entries(entries)
        if any(_host_matches(host, e) for e in deny_entries):
            raise ScopeError(f"target {host!r} is out of scope (explicitly excluded with '!')")
        raise ScopeError(f"target {host!r} is out of scope (not in the allowlist)")
