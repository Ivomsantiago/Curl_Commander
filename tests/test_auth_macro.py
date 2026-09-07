"""Tests for the reusable auth macro (item 1)."""

import asyncio

import httpx
import pytest
import respx

from curlcommander.core.auth_macro import AuthMacro, Session, json_path
from curlcommander.core.request_model import RequestConfig


def _macro(**over):
    data = {
        "name": "login",
        "backend": "http",
        "request": {"method": "POST", "url": "https://api/login", "body_type": "json", "body": "{}"},
        "extract": {"token": {"json": "$.access_token"}},
        "apply": {"header": "Authorization", "template": "Bearer {token}"},
    }
    data.update(over)
    return AuthMacro.from_dict(data)


# --- mini JSONPath --------------------------------------------------------


def test_json_path_subset():
    data = {"access_token": "t", "data": {"token": "d"}, "result": [{"jwt": "j"}]}
    assert json_path(data, "$.access_token") == "t"
    assert json_path(data, "$.data.token") == "d"
    assert json_path(data, "$.result[0].jwt") == "j"
    assert json_path(data, "$.missing") is None
    assert json_path(data, "$.result[9].jwt") is None


# --- apply never mutates + injects header ---------------------------------


def test_apply_injects_and_does_not_mutate():
    macro = _macro()
    macro.session = Session(token="TKN", valid=True)
    cfg = RequestConfig(method="GET", url="https://t/x")
    out = macro.apply(cfg)
    assert out.headers.get("Authorization") == "Bearer TKN"
    assert cfg.headers.get("Authorization") is None  # original untouched


# --- is_stale -------------------------------------------------------------


def test_is_stale_ttl_none_never_expires_by_time():
    macro = _macro(ttl_seconds=None)
    macro.session = Session(token="t", valid=True, acquired_at=0.0)  # ancient
    assert macro.is_stale() is False  # only a die-check can invalidate it
    macro.session.valid = False
    assert macro.is_stale() is True


def test_should_refresh_status_and_regex():
    macro = _macro()
    macro.die_regex = "sess.o expirada"
    r401 = httpx.Response(401)
    result = _to_result(r401, "")
    assert macro.should_refresh(result) is True
    ok_expired = _to_result(httpx.Response(200), "sua sessão expirada, faça login")
    assert macro.should_refresh(ok_expired) is True
    ok = _to_result(httpx.Response(200), "bem-vindo")
    assert macro.should_refresh(ok) is False


def _to_result(resp: httpx.Response, body: str):
    from curlcommander.core.request_model import ResponseResult

    return ResponseResult(resp.status_code, "", {}, body, "", 1.0, len(body), None)


# --- single-flight refresh under concurrency ------------------------------


@respx.mock
async def test_single_flight_login_called_once_under_50_concurrent_401():
    calls = {"n": 0}

    def login_handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"access_token": f"tok{calls['n']}"})

    respx.post("https://api/login").mock(side_effect=login_handler)

    macro = _macro()
    macro.session = Session(token="stale", valid=True)  # everyone saw "stale"

    async def worker():
        await macro.refresh({}, seen_token="stale")

    await asyncio.gather(*[worker() for _ in range(50)])
    assert calls["n"] == 1  # exactly one real login despite 50 concurrent callers
    assert macro.session.token == "tok1"


# --- retry happens exactly once -------------------------------------------


@respx.mock
async def test_fuzz_retry_once_then_propagates():
    from curlcommander.core.fuzzer import run_fuzz

    # Login always issues a fresh token.
    respx.post("https://api/login").mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    # Target always says 401 — so we retry once, and the second 401 must be the
    # final result (no infinite retry loop).
    hits = {"n": 0}

    def target(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(401, text="nope")

    respx.get(url__regex=r"https://t/.*").mock(side_effect=target)

    macro = _macro()
    base = RequestConfig(method="GET", url="https://t/FUZZ")
    results = await run_fuzz(base, [["a"]], auth=macro)
    assert len(results) == 1
    assert results[0].status_code == 401  # propagated, not retried forever
    assert hits["n"] == 2  # original + exactly one retry


# --- config loading errors ------------------------------------------------


@respx.mock
async def test_http_login_extracts_token_and_applies_bearer():
    respx.post("https://api/login").mock(return_value=httpx.Response(200, json={"access_token": "SECRET"}))
    macro = _macro()
    await macro.login({})
    assert macro.session.valid and macro.session.token == "SECRET"
    out = macro.apply(RequestConfig(method="GET", url="https://t/x"))
    assert out.headers.get("Authorization") == "Bearer SECRET"


@respx.mock
async def test_http_login_extracts_and_applies_cookies():
    respx.post("https://api/login").mock(
        return_value=httpx.Response(200, headers={"set-cookie": "sid=abc123; Path=/; HttpOnly"}, json={})
    )
    macro = AuthMacro.from_dict(
        {
            "backend": "http",
            "request": {"method": "POST", "url": "https://api/login"},
            "extract": {"cookies": True},
            "apply": {"cookies": True},
        }
    )
    await macro.login({})
    assert macro.session.cookies.get("sid") == "abc123"
    out = macro.apply(RequestConfig(method="GET", url="https://t/x"))
    assert out.cookies.get("sid") == "abc123"


@respx.mock
async def test_http_login_error_raises():
    from curlcommander.core.auth_macro import AuthMacroError

    respx.post("https://api/login").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(AuthMacroError):
        await _macro().login({})


def test_env_substitution_in_login_body():
    macro = _macro(request={"method": "POST", "url": "https://api/login", "body": '{"u":"{{USER}}"}'})
    cfg = macro._resolved_login_request({"USER": "ada"})
    assert '"u":"ada"' in cfg.body


def test_from_file_rejects_non_object(tmp_path):
    from curlcommander.core.auth_macro import AuthMacroError

    p = tmp_path / "bad.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(AuthMacroError):
        AuthMacro.from_file(str(p))
