"""G.4/G.5 tests: content discovery and bounty-scan (respx)."""

import types

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.core.discovery import discover, expand_words, severity_of
from curlcommander.core.fuzzer import FuzzFilters


def test_expand_words():
    assert expand_words(["a"], ["php", ".bak"]) == ["a", "a.php", "a.bak"]
    assert expand_words(["a"], None) == ["a"]


def test_severity_map():
    assert severity_of("sqli") == "high"
    assert severity_of("xss") == "medium"
    assert severity_of("unknown") == "low"


@respx.mock
async def test_discover_filters_404():
    def handler(request):
        if request.url.path in ("/admin", "/login"):
            return httpx.Response(200, text="ok")
        return httpx.Response(404, text="nope")

    respx.get(url__regex=r"https://t/.*").mock(side_effect=handler)
    results = await discover("https://t", ["admin", "login", "missing"], filters=FuzzFilters(filter_codes={404}))
    found = {r.payloads[-1] for r in results}
    assert found == {"admin", "login"}  # 404s filtered out


@respx.mock
async def test_discover_recursion_one_level():
    def handler(request):
        # /api is a dir; /api/keys exists.
        p = request.url.path
        if p == "/api":
            return httpx.Response(301, text="")
        if p == "/api/keys":
            return httpx.Response(200, text="secret")
        return httpx.Response(404)

    respx.get(url__regex=r"https://t/.*").mock(side_effect=handler)
    results = await discover("https://t", ["api", "keys"], filters=FuzzFilters(filter_codes={404}), recurse=1)
    paths = {r.payloads[-1] for r in results}
    assert "api" in paths
    assert any(p.endswith("api/keys") for p in paths)  # recursed hit, prefixed


def _ns(**kw):
    return types.SimpleNamespace(log_file=None, log_level=None, **kw)


@pytest.fixture(autouse=True)
def _db(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    monkeypatch.setenv("CURLCOMMANDER_PAYLOADS", str(tmp_path / "p"))


@respx.mock
def test_cli_discover_with_payloads(monkeypatch):
    respx.get(url__regex=r"https://t/.*").mock(
        side_effect=lambda r: httpx.Response(200 if r.url.path == "/admin" else 404)
    )
    # Use a builtin category as the wordlist source (traversal has entries).
    monkeypatch.setattr(
        "curlcommander.core.payload_catalog.load_category", lambda cat, all_sources=False: ["admin", "x"]
    )
    rc = runner.run_cli(
        _ns(
            subcommand="discover",
            url="https://t",
            wordlists=[],
            payloads=["traversal"],
            extensions=None,
            recurse=0,
            concurrency=5,
            rate=0.0,
            mc=None,
            fc="404",
            ms=None,
            fs=None,
            mr=None,
            scope=None,
            no_verify=False,
            timeout=5.0,
        )
    )
    assert rc == runner.EXIT_OK


@respx.mock
def test_cli_bounty_scan_requires_engagement():
    rc = runner.run_cli(
        _ns(
            subcommand="bounty-scan",
            url="https://t/x",
            scope=None,
            engagement=None,
            categories="xss",
            concurrency=5,
            rate=0.0,
            no_verify=False,
            timeout=5.0,
        )
    )
    assert rc == runner.EXIT_USAGE


@respx.mock
def test_cli_bounty_scan_runs_and_flags(monkeypatch):
    def handler(request):
        # The SSTI-ish payload triggers a distinct (anomalous) response.
        if "49" in str(request.url) or "{{7" in str(request.url):
            return httpx.Response(500, text="template error 49")
        return httpx.Response(200, text="ok")

    respx.get(url__regex=r"https://t/.*").mock(side_effect=handler)
    monkeypatch.setattr(
        "curlcommander.core.payload_catalog.load_category",
        lambda cat, all_sources=False: ["{{7*7}}", "normal", "safe"],
    )
    rc = runner.run_cli(
        _ns(
            subcommand="bounty-scan",
            url="https://t/x",
            scope=None,
            engagement="ENG-1",
            categories="ssti",
            concurrency=3,
            rate=0.0,
            no_verify=False,
            timeout=5.0,
        )
    )
    assert rc == runner.EXIT_OK
