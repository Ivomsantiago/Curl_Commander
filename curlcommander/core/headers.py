"""Ordered, case- and duplicate-preserving key/value container.

Used for both HTTP request headers and query parameters. A plain ``dict``
collapses duplicate keys, loses insertion order and normalises casing --- all of
which are load-bearing signals in security testing (duplicate ``X-Forwarded-For``
or ``Cookie`` headers, HTTP Parameter Pollution ``?id=1&id=2``, exact header
casing/order for fingerprinting and cache/desync work).

``HeaderList`` stores an explicit ``list[tuple[str, str]]`` so every one of those
properties is preserved and byte-faithful, while still offering enough dict-like
ergonomics (``get``/``__getitem__``/``__setitem__``/``__contains__``) for the
common single-value case and for auth injection.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, Union

PairSource = Union["HeaderList", dict[str, str], Iterable[tuple[str, str]], None]


class HeaderList:
    """A list of ``(key, value)`` pairs preserving order, case and duplicates."""

    __slots__ = ("_items",)

    def __init__(self, items: PairSource = None) -> None:
        self._items: list[tuple[str, str]] = []
        if items is None:
            return
        if isinstance(items, HeaderList):
            self._items = list(items._items)
        elif isinstance(items, dict):
            self._items = [(str(k), str(v)) for k, v in items.items()]
        else:
            self._items = [(str(k), str(v)) for k, v in items]

    # -- mutation -----------------------------------------------------------

    def append(self, key: str, value: str) -> None:
        """Add a pair, always keeping any existing pair with the same key."""
        self._items.append((str(key), str(value)))

    # ``add`` reads naturally for "add another one of these".
    add = append

    def set(self, key: str, value: str) -> None:
        """Replace the first case-insensitive match in place, else append.

        This is the "there should be exactly one" semantics used by auth
        injection and default-header logic. Use :meth:`append` to deliberately
        add duplicates.
        """
        lowered = key.lower()
        for i, (k, _v) in enumerate(self._items):
            if k.lower() == lowered:
                self._items[i] = (k, str(value))
                # Drop any further duplicates so "set" really means one.
                self._items = [p for j, p in enumerate(self._items) if j == i or p[0].lower() != lowered]
                return
        self._items.append((str(key), str(value)))

    def __setitem__(self, key: str, value: str) -> None:
        self.set(key, value)

    def setdefault(self, key: str, value: str) -> str:
        existing = self.get(key)
        if existing is not None:
            return existing
        self.append(key, value)
        return value

    def remove_all(self, key: str) -> None:
        lowered = key.lower()
        self._items = [p for p in self._items if p[0].lower() != lowered]

    def __delitem__(self, key: str) -> None:
        self.remove_all(key)

    # -- read ---------------------------------------------------------------

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the last case-insensitive match, or ``default``."""
        lowered = key.lower()
        result: str | None = default
        for k, v in self._items:
            if k.lower() == lowered:
                result = v
        return result

    def get_all(self, key: str) -> list[str]:
        lowered = key.lower()
        return [v for k, v in self._items if k.lower() == lowered]

    def __getitem__(self, key: str) -> str:
        lowered = key.lower()
        found = False
        result = ""
        for k, v in self._items:
            if k.lower() == lowered:
                found = True
                result = v
        if not found:
            raise KeyError(key)
        return result

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        lowered = key.lower()
        return any(k.lower() == lowered for k, _ in self._items)

    def keys(self) -> list[str]:
        return [k for k, _ in self._items]

    def items(self) -> list[tuple[str, str]]:
        return list(self._items)

    def as_tuples(self) -> list[tuple[str, str]]:
        """Alias for :meth:`items`; the shape httpx accepts directly."""
        return list(self._items)

    def to_dict(self) -> dict[str, str]:
        """Lossy dict view (last value wins). For display/compat only."""
        return dict(self._items)

    def to_jsonable(self) -> list[list[str]]:
        return [[k, v] for k, v in self._items]

    @classmethod
    def from_jsonable(cls, data: Any) -> HeaderList:
        if not data:
            return cls()
        return cls([(str(k), str(v)) for k, v in data])

    def copy(self) -> HeaderList:
        return HeaderList(self)

    # -- dunder -------------------------------------------------------------

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, HeaderList):
            return self._items == other._items
        if isinstance(other, (dict, list, tuple)):
            try:
                return self._items == HeaderList(other)._items  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return NotImplemented  # type: ignore[return-value]
        return NotImplemented  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"HeaderList({self._items!r})"


def coerce(items: PairSource) -> HeaderList:
    """Coerce dict / list-of-pairs / HeaderList / None into a HeaderList."""
    return items if isinstance(items, HeaderList) else HeaderList(items)
