"""Tests for the ordered, case- and duplicate-preserving header/param model."""

import httpx
import respx

from curlcommander.core.curl_builder import build_curl
from curlcommander.core.headers import HeaderList
from curlcommander.core.http_client import send
from curlcommander.core.request_model import HistoryEntry, RequestConfig
from curlcommander.storage.history_repo import HistoryRepo


def test_headerlist_preserves_order_case_and_duplicates():
    h = HeaderList()
    h.append("X-Forwarded-For", "127.0.0.1")
    h.append("X-Forwarded-For", "10.0.0.1")
    h.append("host", "internal")
    assert h.items() == [
        ("X-Forwarded-For", "127.0.0.1"),
        ("X-Forwarded-For", "10.0.0.1"),
        ("host", "internal"),
    ]
    assert h.get_all("x-forwarded-for") == ["127.0.0.1", "10.0.0.1"]
    assert h.get("host") == "internal"  # case-insensitive lookup, original case kept


def test_set_replaces_but_append_duplicates():
    h = HeaderList([("A", "1"), ("A", "2")])
    h.set("a", "9")
    # value replaced, first-seen key casing preserved, duplicate collapsed
    assert h.items() == [("A", "9")]
    h.append("A", "3")
    assert h.get_all("a") == ["9", "3"]


def test_curl_builder_emits_duplicate_headers():
    cfg = RequestConfig(
        method="GET",
        url="https://x/y",
        headers=[("X-Forwarded-For", "1.1.1.1"), ("X-Forwarded-For", "2.2.2.2")],
    )
    cmd = build_curl(cfg)
    assert cmd.count("X-Forwarded-For: 1.1.1.1") == 1
    assert cmd.count("X-Forwarded-For: 2.2.2.2") == 1


def test_curl_builder_emits_duplicate_params_hpp():
    cfg = RequestConfig(
        method="GET",
        url="https://x/y",
        params=[("id", "1"), ("id", "2")],
    )
    cmd = build_curl(cfg)
    assert "id=1&id=2" in cmd


@respx.mock
async def test_duplicate_headers_and_params_reach_the_wire():
    route = respx.get("https://x/y").mock(return_value=httpx.Response(200, text="ok"))
    cfg = RequestConfig(
        method="GET",
        url="https://x/y",
        headers=[("X-Dup", "a"), ("X-Dup", "b")],
        params=[("id", "1"), ("id", "2")],
    )
    await send(cfg)
    sent = route.calls.last.request
    assert sent.headers.get_list("x-dup") == ["a", "b"]
    assert str(sent.url).count("id=") == 2


def test_storage_round_trips_duplicates():
    repo = HistoryRepo(db_path=":memory:")
    cfg = RequestConfig(
        method="GET",
        url="https://x/y",
        headers=[("Cookie", "a=1"), ("Cookie", "b=2")],
        params=[("q", "x"), ("q", "y")],
    )
    entry = HistoryEntry(id=0, timestamp="t", request=cfg, status_code=200, duration_ms=1.0, curl_cmd="")
    fetched = repo.get_by_id(repo.save(entry))
    assert fetched is not None
    assert fetched.request.headers.get_all("Cookie") == ["a=1", "b=2"]
    assert fetched.request.params.get_all("q") == ["x", "y"]


def test_request_config_to_from_dict_round_trip():
    cfg = RequestConfig(
        method="POST",
        url="https://x/y",
        headers=[("A", "1"), ("A", "2")],
        params=[("p", "v")],
        body="x",
        body_type="raw",
        timeout=12.5,
        max_retries=3,
    )
    rebuilt = RequestConfig.from_dict(cfg.to_dict())
    assert rebuilt.to_dict() == cfg.to_dict()
    assert rebuilt.headers.get_all("A") == ["1", "2"]
