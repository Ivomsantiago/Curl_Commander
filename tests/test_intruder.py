"""Tests for the Intruder attack-mode mapping onto the fuzz engine."""

import httpx
import pytest
import respx

from curlcommander.core.intruder import ATTACK_MODES, marker_scheme, run_attack
from curlcommander.core.request_model import RequestConfig


def test_marker_scheme_by_mode():
    assert marker_scheme("battering-ram", 3) == ["FUZZ", "FUZZ", "FUZZ"]
    assert marker_scheme("cluster-bomb", 2) == ["FUZZ1", "FUZZ2"]
    assert marker_scheme("sniper", 2) == ["FUZZ1", "FUZZ2"]
    assert set(ATTACK_MODES) == {"sniper", "battering-ram", "pitchfork", "cluster-bomb"}


@respx.mock
async def test_cluster_bomb_runs_all_combinations():
    respx.get(url__regex=r"https://t/x.*").mock(return_value=httpx.Response(200, text="ok"))
    base = RequestConfig(method="GET", url="https://t/x?a=FUZZ1&b=FUZZ2")
    results = await run_attack(base, "cluster-bomb", [["1", "2"], ["9"]])
    assert len(results) == 2  # 2 x 1 combinations


@respx.mock
async def test_pitchfork_advances_in_lockstep():
    respx.get(url__regex=r"https://t/x.*").mock(return_value=httpx.Response(200, text="ok"))
    base = RequestConfig(method="GET", url="https://t/x?a=FUZZ1&b=FUZZ2")
    results = await run_attack(base, "pitchfork", [["1", "2"], ["8", "9"]])
    assert len(results) == 2  # zip, not product


@respx.mock
async def test_battering_ram_one_value_all_positions():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")

    respx.get(url__regex=r"https://t/x.*").mock(side_effect=handler)
    base = RequestConfig(method="GET", url="https://t/x?a=FUZZ&b=FUZZ")
    results = await run_attack(base, "battering-ram", [["PWN"]])
    assert len(results) == 1
    assert "a=PWN" in seen[0] and "b=PWN" in seen[0]  # same value in both


@respx.mock
async def test_sniper_one_position_at_a_time():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text="ok")

    respx.get(url__regex=r"https://t/x.*").mock(side_effect=handler)
    base = RequestConfig(method="GET", url="https://t/x?a=FUZZ1&b=FUZZ2")
    results = await run_attack(base, "sniper", [["P"]], originals=["orig_a", "orig_b"])
    # 2 positions x 1 payload = 2 requests; each keeps the other at its original.
    assert len(results) == 2
    assert any("a=P" in u and "b=orig_b" in u for u in seen)
    assert any("b=P" in u and "a=orig_a" in u for u in seen)


async def test_run_attack_rejects_unknown_mode_and_empty_wordlist():
    base = RequestConfig(method="GET", url="https://t/x?a=FUZZ")
    with pytest.raises(ValueError):
        await run_attack(base, "nope", [["1"]])
    with pytest.raises(ValueError):
        await run_attack(base, "sniper", [[]])


def test_gui_summarize_reports_distribution_and_anomalies():
    from curlcommander.core.fuzzer import FuzzResult
    from curlcommander.gui.intruder_panel import _summarize

    results = [
        FuzzResult(payloads=["a"], status_code=200, size_bytes=10, duration_ms=5.0, matched_regex=False),
        FuzzResult(payloads=["b"], status_code=200, size_bytes=10, duration_ms=5.0, matched_regex=False),
        FuzzResult(payloads=["c"], status_code=500, size_bytes=99, duration_ms=9.0, matched_regex=False, anomaly=True),
        FuzzResult(payloads=["d"], status_code=None, size_bytes=0, duration_ms=1.0, matched_regex=False, error="boom"),
    ]
    out = _summarize(results)
    assert "4" in out  # total
    assert "1" in out  # one anomaly
    assert "200×2" in out
    assert "500×1" in out
    assert "erro" in out


def test_gui_summarize_empty():
    from curlcommander.gui.intruder_panel import _summarize

    assert "Nenhum" in _summarize([])
