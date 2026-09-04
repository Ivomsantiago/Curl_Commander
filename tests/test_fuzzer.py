"""Tests for 2B.3 fuzzing and encoders."""

import httpx
import pytest
import respx

from curlcommander.core.encoders import apply_encoders, available
from curlcommander.core.fuzzer import (
    FuzzFilters,
    find_markers,
    markers_for,
    run_fuzz,
    substitute,
)
from curlcommander.core.request_model import RequestConfig

# --- encoders -------------------------------------------------------------


def test_encoders_available():
    assert {"url", "double-url", "base64", "hex", "html-entity", "unicode"} <= set(available())


def test_encoder_chain():
    assert apply_encoders("a b", ["url"]) == "a%20b"
    assert apply_encoders("../", ["double-url"]) == "..%252F"
    assert apply_encoders("A", ["base64"]) == "QQ=="
    assert apply_encoders("AB", ["hex"]) == "4142"


def test_encoder_unknown_raises():
    with pytest.raises(KeyError):
        apply_encoders("x", ["nope"])


# --- marker handling ------------------------------------------------------


def test_markers_and_find():
    assert markers_for(1) == ["FUZZ"]
    assert markers_for(2) == ["FUZZ1", "FUZZ2"]
    cfg = RequestConfig(method="GET", url="https://x/FUZZ1", headers=[("X", "FUZZ2")])
    assert find_markers(cfg, markers_for(2)) == ["FUZZ1", "FUZZ2"]


def test_substitute_replaces_everywhere():
    cfg = RequestConfig(
        method="GET",
        url="https://x/FUZZ",
        headers=[("H", "FUZZ")],
        params=[("p", "FUZZ")],
        body="FUZZ",
    )
    out = substitute(cfg, {"FUZZ": "PWN"})
    assert out.url == "https://x/PWN"
    assert out.headers.get("H") == "PWN"
    assert out.params.get("p") == "PWN"
    assert out.body == "PWN"


# --- engine ---------------------------------------------------------------


@respx.mock
async def test_fuzz_runs_all_payloads_and_flags_anomaly():
    def handler(request):
        # /admin returns 200, everything else 404 -> /admin is the anomaly.
        if request.url.path == "/admin":
            return httpx.Response(200, text="secret area")
        return httpx.Response(404, text="nope")

    respx.get(url__regex=r"https://x/.*").mock(side_effect=handler)

    base = RequestConfig(method="GET", url="https://x/FUZZ")
    results = await run_fuzz(base, [["home", "admin", "about"]], concurrency=3)
    assert len(results) == 3
    anomalies = [r for r in results if r.anomaly]
    assert len(anomalies) == 1 and anomalies[0].payloads == ["admin"]


@respx.mock
async def test_fuzz_filters_by_code():
    def handler(request):
        return httpx.Response(200 if request.url.path == "/ok" else 500, text="x")

    respx.get(url__regex=r"https://x/.*").mock(side_effect=handler)
    base = RequestConfig(method="GET", url="https://x/FUZZ")
    results = await run_fuzz(base, [["ok", "bad"]], filters=FuzzFilters(match_codes={200}))
    assert [r.payloads[0] for r in results] == ["ok"]


@respx.mock
async def test_fuzz_clusterbomb_two_lists():
    respx.get(url__regex=r"https://x/.*").mock(return_value=httpx.Response(200, text="x"))
    base = RequestConfig(method="GET", url="https://x/FUZZ1/FUZZ2")
    results = await run_fuzz(base, [["a", "b"], ["1", "2"]], mode="clusterbomb")
    assert len(results) == 4  # cartesian product
