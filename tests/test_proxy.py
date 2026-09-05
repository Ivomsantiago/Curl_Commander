"""H.4 tests: intercepting-proxy logic (rules, scope, addon via mitmproxy tflow)."""

import re

import pytest

from curlcommander.core import proxy
from curlcommander.core.proxy import (
    MatchReplace,
    apply_replacements,
    ignore_hosts_regex,
    parse_rule,
    proxy_available,
)
from curlcommander.storage.history_repo import HistoryRepo

pytestmark = pytest.mark.skipif(not proxy_available(), reason="mitmproxy not installed")


# --- pure logic -----------------------------------------------------------


def test_parse_rule_variants():
    r = parse_rule("resp:secret==>REDACTED")
    assert r.pattern == "secret" and r.replacement == "REDACTED" and r.where == "resp"
    r2 = parse_rule("foo==>bar")
    assert r2.where == "both"


def test_parse_rule_invalid():
    with pytest.raises(proxy.ProxyError):
        parse_rule("no-arrow-here")


def test_apply_replacements_side_aware():
    rules = [MatchReplace("a", "X", "resp")]
    assert apply_replacements(b"aaa", rules, is_request=False) == b"XXX"
    assert apply_replacements(b"aaa", rules, is_request=True) == b"aaa"  # req side untouched


def test_ignore_hosts_regex_tunnels_out_of_scope():
    rx = ignore_hosts_regex(["api.target.com"])
    assert rx is not None
    # ignore_hosts matches hosts to TUNNEL (not intercept).
    assert re.search(rx, "evil.com:443")  # out of scope -> tunnelled
    assert not re.search(rx, "api.target.com:443")  # in scope -> intercepted


def test_ignore_hosts_none_without_scope():
    assert ignore_hosts_regex([]) is None


# --- addon behaviour via mitmproxy test flows -----------------------------


def _flow(url: str, body: bytes = b""):
    from mitmproxy.test import tflow, tutils

    f = tflow.tflow(resp=tutils.tresp())
    parts = url.split("://", 1)[1]
    host = parts.split("/", 1)[0]
    f.request.scheme = "https"
    f.request.host = host.split(":")[0]
    f.request.port = 443
    f.request.path = "/" + (parts.split("/", 1)[1] if "/" in parts else "")
    if body:
        f.response.content = body
    return f


def test_addon_rewrites_and_captures_in_scope():
    repo = HistoryRepo(db_path=":memory:")
    addon = proxy.build_addon(["example.com"], [MatchReplace("secret", "REDACTED", "resp")], repo, engagement="ENG-1")
    f = _flow("https://example.com/x", body=b"a secret token")
    addon.response(f)
    assert f.response.content == b"a REDACTED token"  # match-and-replace applied
    assert repo.load()  # captured to history
    repo.close()


def test_addon_ignores_out_of_scope():
    repo = HistoryRepo(db_path=":memory:")
    addon = proxy.build_addon(["example.com"], [MatchReplace("secret", "X", "resp")], repo)
    f = _flow("https://evil.com/x", body=b"a secret token")
    addon.response(f)
    assert f.response.content == b"a secret token"  # untouched
    assert repo.load() == []  # not captured
    repo.close()


def test_ca_dir_created_restricted(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path / "cc"))
    import importlib

    from curlcommander import config as cfg

    importlib.reload(cfg)
    d = proxy.ca_dir()
    assert d.exists()
    importlib.reload(cfg)
