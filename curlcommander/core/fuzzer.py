"""Request fuzzing engine (2B.3).

Markers (``FUZZ`` for a single wordlist, ``FUZZ1``/``FUZZ2``/... for several)
placed anywhere in the request --- URL, header/param/cookie value, or body ---
are replaced with wordlist entries. Multiple wordlists combine as clusterbomb
(cartesian product, like ffuf) or pitchfork (zipped). Results are filtered
(match/filter by code, size, regex) and deviations from the baseline are
flagged as anomalies.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import product

from curlcommander.core.encoders import apply_encoders
from curlcommander.core.headers import HeaderList
from curlcommander.core.http_client import send
from curlcommander.core.request_model import RequestConfig


@dataclass
class FuzzResult:
    payloads: list[str]
    status_code: int | None
    size_bytes: int
    duration_ms: float
    matched_regex: bool
    error: str | None = None
    anomaly: bool = False


@dataclass
class FuzzFilters:
    match_codes: set[int] | None = None
    filter_codes: set[int] | None = None
    match_size: int | None = None
    filter_size: int | None = None
    match_regex: str | None = None

    def keep(self, result: FuzzResult) -> bool:
        code = result.status_code
        if self.match_codes is not None and code not in self.match_codes:
            return False
        if self.filter_codes is not None and code in self.filter_codes:
            return False
        if self.match_size is not None and result.size_bytes != self.match_size:
            return False
        if self.filter_size is not None and result.size_bytes == self.filter_size:
            return False
        if self.match_regex is not None and not result.matched_regex:
            return False
        return True


def markers_for(count: int) -> list[str]:
    return ["FUZZ"] if count == 1 else [f"FUZZ{i + 1}" for i in range(count)]


def find_markers(config: RequestConfig, markers: list[str]) -> list[str]:
    haystack = "\n".join(
        [config.url, config.body]
        + [v for _, v in config.headers]
        + [v for _, v in config.params]
        + [v for _, v in config.cookies]
    )
    return [m for m in markers if m in haystack]


def substitute(config: RequestConfig, mapping: dict[str, str]) -> RequestConfig:
    def sub(text: str) -> str:
        for marker, value in mapping.items():
            text = text.replace(marker, value)
        return text

    clone = RequestConfig.from_dict(config.to_dict())
    clone.url = sub(config.url)
    clone.body = sub(config.body)
    clone.headers = HeaderList([(k, sub(v)) for k, v in config.headers])
    clone.params = HeaderList([(k, sub(v)) for k, v in config.params])
    clone.cookies = HeaderList([(k, sub(v)) for k, v in config.cookies])
    return clone


def _combinations(wordlists: list[list[str]], mode: str) -> Iterator[tuple[str, ...]]:
    if mode == "pitchfork":
        return zip(*wordlists, strict=False)
    return product(*wordlists)  # clusterbomb (default)


class _RateLimiter:
    """Simple async rate limiter: at most `rate` starts per second (0 = off)."""

    def __init__(self, rate: float) -> None:
        self._interval = 1.0 / rate if rate and rate > 0 else 0.0
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next - now)
            self._next = max(now, self._next) + self._interval
        if sleep_for:
            await asyncio.sleep(sleep_for)


async def run_fuzz(
    base: RequestConfig,
    wordlists: list[list[str]],
    mode: str = "clusterbomb",
    filters: FuzzFilters | None = None,
    concurrency: int = 10,
    rate: float = 0.0,
    encoders: list[str] | None = None,
) -> list[FuzzResult]:
    filters = filters or FuzzFilters()
    markers = markers_for(len(wordlists))
    regex = re.compile(filters.match_regex) if filters.match_regex else None

    semaphore = asyncio.Semaphore(max(1, concurrency))
    limiter = _RateLimiter(rate)

    async def one(payloads: tuple[str, ...]) -> FuzzResult:
        encoded = [apply_encoders(p, encoders) if encoders else p for p in payloads]
        mapping = dict(zip(markers, encoded, strict=False))
        cfg = substitute(base, mapping)
        async with semaphore:
            await limiter.wait()
            result = await send(cfg)
        matched = bool(regex.search(result.body)) if regex else False
        return FuzzResult(
            payloads=list(payloads),
            status_code=result.status_code,
            size_bytes=result.size_bytes,
            duration_ms=result.duration_ms,
            matched_regex=matched,
            error=result.error,
        )

    tasks = [one(combo) for combo in _combinations(wordlists, mode)]
    results = await asyncio.gather(*tasks)

    kept = [r for r in results if filters.keep(r)]
    _flag_anomalies(kept)
    return kept


def _flag_anomalies(results: list[FuzzResult]) -> None:
    """Mark results that deviate from the most common (status, size) baseline."""
    if len(results) < 2:
        return
    baseline = Counter((r.status_code, r.size_bytes) for r in results).most_common(1)[0][0]
    for r in results:
        r.anomaly = (r.status_code, r.size_bytes) != baseline
