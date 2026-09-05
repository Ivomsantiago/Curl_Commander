"""G.2/G.3 tests: catalog resolution, category load, search, CLI."""

import types

import pytest

from curlcommander.cli import runner
from curlcommander.core import payload_catalog as cat


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    # A fake synced seclists tree under the payloads root.
    root = tmp_path / "data"
    monkeypatch.setenv("CURLCOMMANDER_PAYLOADS", str(root))
    monkeypatch.delenv("SECLISTS_PATH", raising=False)
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    seclists = root / "seclists" / "Fuzzing" / "XSS"
    seclists.mkdir(parents=True)
    (seclists / "xss.txt").write_text("<svg onload=alert(1)>\n<img src=x onerror=alert(1)>\n")
    (root / "seclists" / "Discovery").mkdir(parents=True)
    (root / "seclists" / "Discovery" / "common.txt").write_text("admin\nlogin\nrobots.txt\n")
    return root


def test_categories_include_curated():
    assert {"xss", "sqli", "traversal", "lfi", "ssrf"} <= set(cat.categories())


def test_resolve_spec_seclists_path():
    lines = cat.resolve_spec("seclists:Discovery/common.txt")
    assert "admin" in lines and "robots.txt" in lines


def test_resolve_spec_unsynced_source_errors():
    with pytest.raises(cat.CatalogError):
        cat.resolve_spec("fuzzdb:some/list.txt")


def test_resolve_spec_plain_file(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("a\nb\n")
    assert cat.resolve_spec(str(f)) == ["a", "b"]


def test_load_category_builtin_only():
    # Without --all, builtin xss.txt is used (embedded, always present).
    lines = cat.load_category("xss", all_sources=False)
    assert lines and any("alert" in x for x in lines)


def test_load_category_all_sources_dedup():
    lines = cat.load_category("xss", all_sources=True)
    # Includes both the embedded set and the synced seclists file.
    assert any("onload=alert(1)" in x for x in lines)
    assert len(lines) == len(set(lines))  # deduped


def test_search_finds_synced_and_builtin():
    hits = cat.search("common")
    assert any(h.startswith("seclists:") and "common.txt" in h for h in hits)
    hits2 = cat.search("sqli")
    assert any(h == "builtin:sqli" for h in hits2)


# --- CLI ------------------------------------------------------------------


def _ns(**kw):
    return types.SimpleNamespace(subcommand="payloads", log_file=None, log_level=None, **kw)


def test_cli_payloads_list():
    assert runner.run_cli(_ns(payloads_cmd="list", category=None)) == runner.EXIT_OK


def test_cli_payloads_show_count():
    assert (
        runner.run_cli(_ns(payloads_cmd="show", category="xss", limit=5, count=True, all_sources=False))
        == runner.EXIT_OK
    )


def test_cli_payloads_show_unknown_category():
    rc = runner.run_cli(_ns(payloads_cmd="show", category="nope", limit=5, count=False, all_sources=False))
    assert rc == runner.EXIT_USAGE


def test_cli_payloads_search():
    assert runner.run_cli(_ns(payloads_cmd="search", term="common")) == runner.EXIT_OK
