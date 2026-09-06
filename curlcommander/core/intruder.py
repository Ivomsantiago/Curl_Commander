"""Burp-style Intruder attack modes on top of the existing fuzz engine.

The GUI marks attack positions on a request; each position becomes a fuzz
marker (``FUZZ``/``FUZZ1``/…) that ``core.fuzzer`` already understands. This
module only maps the four named Burp modes onto that engine — it adds no new
request logic:

- **sniper**        one wordlist, one position at a time (others revert to their
                    original value); the classic single-payload sweep.
- **battering-ram** one wordlist, the same value in *every* position at once.
- **pitchfork**     one wordlist per position, advanced in lockstep (zip).
- **cluster-bomb**  one wordlist per position, every combination (cartesian).

pitchfork/cluster-bomb are exactly the engine's existing multi-wordlist modes;
sniper/battering-ram are thin variations of how the markers are placed.
"""

from __future__ import annotations

from curlcommander.core.fuzzer import (
    FuzzFilters,
    FuzzResult,
    _flag_anomalies,
    markers_for,
    run_fuzz,
    substitute,
)
from curlcommander.core.request_model import RequestConfig

ATTACK_MODES: tuple[str, ...] = ("sniper", "battering-ram", "pitchfork", "cluster-bomb")


def marker_scheme(mode: str, n_positions: int) -> list[str]:
    """The marker name to place at each of ``n_positions`` for a given mode.

    Battering-ram uses the *same* marker everywhere (one value fills all
    positions at once); every other mode uses distinct markers.
    """
    if mode == "battering-ram":
        return ["FUZZ"] * n_positions
    return markers_for(n_positions)


async def run_attack(
    base: RequestConfig,
    mode: str,
    wordlists: list[list[str]],
    originals: list[str] | None = None,
    filters: FuzzFilters | None = None,
    concurrency: int = 10,
    rate: float = 0.0,
    encoders: list[str] | None = None,
) -> list[FuzzResult]:
    """Run an Intruder attack. ``base`` already carries the markers (see
    :func:`marker_scheme`); ``originals`` (sniper only) are the pre-marker
    literals so the non-attacked positions can be reverted.
    """
    if mode not in ATTACK_MODES:
        raise ValueError(f"unknown attack mode: {mode!r} (known: {', '.join(ATTACK_MODES)})")
    if not wordlists or any(not wl for wl in wordlists):
        raise ValueError("a wordlist is empty or missing")

    common = {"filters": filters, "concurrency": concurrency, "rate": rate, "encoders": encoders}

    if mode == "pitchfork":
        return await run_fuzz(base, wordlists, "pitchfork", **common)  # type: ignore[arg-type]
    if mode == "cluster-bomb":
        return await run_fuzz(base, wordlists, "clusterbomb", **common)  # type: ignore[arg-type]
    if mode == "battering-ram":
        # One marker (FUZZ) sits in every position; a single wordlist fills them.
        return await run_fuzz(base, [wordlists[0]], "clusterbomb", **common)  # type: ignore[arg-type]

    # sniper: distinct markers, one wordlist, one position at a time.
    originals = originals or []
    markers = markers_for(len(originals))
    wordlist = wordlists[0]
    results: list[FuzzResult] = []
    for i, marker in enumerate(markers):
        # Revert every OTHER position to its literal and relabel the active one
        # to bare FUZZ, so a single-wordlist run fuzzes only this position.
        mapping = {mk: originals[j] for j, mk in enumerate(markers) if j != i}
        mapping[marker] = "FUZZ"
        cfg = substitute(base, mapping)
        results.extend(await run_fuzz(cfg, [wordlist], "clusterbomb", **common))  # type: ignore[arg-type]
    _flag_anomalies(results)
    return results
