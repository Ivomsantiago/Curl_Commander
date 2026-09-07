"""Tests for the IDOR / BOLA authorization correlation workflow (item 3)."""

import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.core.auth_macro import AuthMacro, Session
from curlcommander.core.idor import (
    BLOCKED,
    CONFIRMED,
    SUSPECT,
    _classify,
    check_idor,
    enumerate_range,
)
from curlcommander.core.request_model import RequestConfig


def _macro(token: str) -> AuthMacro:
    """A ready-to-use macro whose session is already valid (no login roundtrip)."""
    m = AuthMacro.from_dict(
        {
            "name": token,
            "backend": "http",
            "apply": {"header": "Authorization", "template": "Bearer {token}"},
        }
    )
    m.session = Session(token=token, valid=True)
    return m


# --- pure classifier ------------------------------------------------------


def test_classify_confirmed_when_b_mirrors_a():
    f = _classify("101", 200, 200, 0.99, 0.85)
    assert f.verdict == CONFIRMED


def test_classify_blocked_on_denied_status():
    for status in (401, 403, 404):
        assert _classify("101", 200, status, 0.10, 0.85).verdict == BLOCKED


def test_classify_suspect_for_middle_ground():
    # B got 200 but the body diverges — not conclusive, needs a human.
    f = _classify("101", 200, 200, 0.40, 0.85)
    assert f.verdict == SUSPECT


def test_classify_low_similarity_200_is_not_confirmed():
    # A 200 that does not resemble A's body must never auto-confirm.
    assert _classify("101", 200, 200, 0.84, 0.85).verdict == SUSPECT


# --- end-to-end A/B correlation over HTTP ---------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_check_idor_confirmed_when_b_sees_as():
    body = '{"id": 101, "owner": "alice", "balance": 42}'

    def handler(request: httpx.Request) -> httpx.Response:
        # Both identities get the SAME resource back → broken access control.
        return httpx.Response(200, text=body)

    respx.get("https://api/orders/101").mock(side_effect=handler)

    template = RequestConfig(method="GET", url="https://api/orders/RESOURCE_ID")
    findings = await check_idor(template, ["101"], _macro("A"), _macro("B"))
    assert len(findings) == 1
    assert findings[0].verdict == CONFIRMED
    assert findings[0].similarity == pytest.approx(1.0)


@pytest.mark.asyncio
@respx.mock
async def test_check_idor_blocked_when_b_denied():
    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization", "")
        if auth == "Bearer A":
            return httpx.Response(200, text='{"id": 101, "owner": "alice"}')
        return httpx.Response(403, text='{"error": "forbidden"}')

    respx.get("https://api/orders/101").mock(side_effect=handler)

    template = RequestConfig(method="GET", url="https://api/orders/RESOURCE_ID")
    findings = await check_idor(template, ["101"], _macro("A"), _macro("B"))
    assert findings[0].verdict == BLOCKED
    assert findings[0].status_b == 403


# --- edge case: a session that never authenticates ------------------------


@pytest.mark.asyncio
@respx.mock
async def test_check_idor_no_auth_both_identities_same():
    # No auth macros at all: both requests are identical, so a shared 200 is
    # reported as CONFIRMED-shaped only when bodies match — here it is a login
    # wall (401) for both, which must classify as BLOCKED, never confirmed.
    respx.get("https://api/orders/101").mock(return_value=httpx.Response(401, text="login required"))
    template = RequestConfig(method="GET", url="https://api/orders/RESOURCE_ID")
    findings = await check_idor(template, ["101"], None, None)
    assert findings[0].verdict == BLOCKED


# --- horizontal enumeration reuses the fuzzer -----------------------------


@pytest.mark.asyncio
@respx.mock
async def test_enumerate_range_reaches_ids():
    for i in range(1000, 1004):
        respx.get(f"https://api/orders/{i}").mock(return_value=httpx.Response(200, text=f"order {i}"))

    template = RequestConfig(method="GET", url="https://api/orders/RESOURCE_ID")
    results = await enumerate_range(template, 1000, 1003, concurrency=4)
    assert len(results) == 4
    assert all(r.status_code == 200 for r in results)


# --- CLI runner dispatch --------------------------------------------------


def _idor_args(**over):
    base = dict(
        kind="idor",
        url="https://api/orders/RESOURCE_ID",
        method="GET",
        engagement="ENG",
        scope=None,
        no_verify=False,
        timeout=30.0,
        evidence=None,
        ids="101",
        auth_a=None,
        auth_b=None,
        threshold=0.85,
        fuzz_range=None,
        session_die_regex=None,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@respx.mock
def test_run_idor_confirmed_and_enumerates(capsys):
    respx.get("https://api/orders/101").mock(return_value=httpx.Response(200, text='{"id":101}'))
    for i in range(1000, 1003):
        respx.get(f"https://api/orders/{i}").mock(return_value=httpx.Response(200, text=f"o{i}"))

    code = runner._run_validate(_idor_args(fuzz_range="1000-1002"))
    out = capsys.readouterr().out
    assert code == runner.EXIT_OK
    assert "CONFIRMED" in out
    assert "3/3" in out  # horizontal enumeration reached all three


def test_run_idor_requires_ids(capsys):
    code = runner._run_validate(_idor_args(ids=""))
    assert code == runner.EXIT_USAGE
    assert "--ids" in capsys.readouterr().out


def test_run_idor_requires_marker(capsys):
    code = runner._run_validate(_idor_args(url="https://api/orders/101"))
    assert code == runner.EXIT_USAGE
    assert "RESOURCE_ID" in capsys.readouterr().out
