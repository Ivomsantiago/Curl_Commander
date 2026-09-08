"""Tests for external recon tool orchestration (item 7): subfinder/httpx/nuclei/katana."""

import json
import os
import stat
import types
from pathlib import Path

import pytest

from curlcommander.cli import runner
from curlcommander.core import scope
from curlcommander.core.recon import scan
from curlcommander.core.recon.tools import TOOLS, ReconToolError, available, require, run_and_stream

# --- tool detection ---------------------------------------------------------


def test_available_false_when_not_on_path(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    for name in TOOLS:
        assert not available(name)


def test_require_raises_with_install_hint(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(ReconToolError, match="go install"):
        require("subfinder")


def test_require_unknown_tool_raises():
    with pytest.raises(ReconToolError):
        require("not-a-real-tool")


# --- run_and_stream over a fake binary --------------------------------------


def _fake_binary(tmp_path: Path, lines: list[str]) -> Path:
    """A tiny executable script that prints each line to stdout, then exits."""
    script = tmp_path / "fake-tool"
    body = "#!/usr/bin/env python3\n" + "\n".join(f"print({ln!r})" for ln in lines) + "\n"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.mark.asyncio
async def test_run_and_stream_parses_json_lines_and_skips_bad_ones(tmp_path, monkeypatch):
    script = _fake_binary(
        tmp_path,
        [
            json.dumps({"host": "a.example.com"}),
            "not json at all",  # must be skipped, not raised
            json.dumps("a bare json string"),  # valid JSON but not a dict -> skipped
            json.dumps({"host": "b.example.com"}),
        ],
    )
    monkeypatch.setattr("shutil.which", lambda name: str(script))
    records = [r async for r in run_and_stream("subfinder", ["-d", "example.com"])]
    assert records == [{"host": "a.example.com"}, {"host": "b.example.com"}]


@pytest.mark.asyncio
async def test_run_and_stream_missing_binary_raises_before_spawning(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(ReconToolError):
        async for _ in run_and_stream("httpx", ["-l", "x.txt"]):
            pass


# --- scope filtering ---------------------------------------------------------


def test_filter_scope_no_entries_keeps_everything():
    batch = scan.filter_scope(["a.com", "b.com"], None, is_url=False)
    assert batch.kept == ["a.com", "b.com"]
    assert batch.dropped == 0


def test_filter_scope_drops_out_of_scope_hosts():
    batch = scan.filter_scope(["a.target.com", "evil.com"], ["*.target.com"], is_url=False)
    assert batch.kept == ["a.target.com"]
    assert batch.dropped == 1


def test_filter_scope_urls():
    batch = scan.filter_scope(["https://a.target.com/x", "https://evil.com/y"], ["*.target.com"], is_url=True)
    assert batch.kept == ["https://a.target.com/x"]
    assert batch.dropped == 1


# --- per-tool workflows -------------------------------------------------------


@pytest.mark.asyncio
async def test_subfinder_refuses_out_of_scope_domain():
    with pytest.raises(scope.ScopeError):
        async for _ in scan.subfinder("evil.com", ["only.allowed.com"]):
            pass


@pytest.mark.asyncio
async def test_subfinder_runs_when_in_scope(tmp_path, monkeypatch):
    script = _fake_binary(tmp_path, [json.dumps({"host": "api.target.com"})])
    monkeypatch.setattr("shutil.which", lambda name: str(script))
    records = [r async for r in scan.subfinder("target.com", ["target.com", "*.target.com"])]
    assert records == [{"host": "api.target.com"}]


@pytest.mark.asyncio
async def test_httpx_probe_never_writes_out_of_scope_hosts_to_the_input_file(tmp_path, monkeypatch):
    captured_args: list[list[str]] = []

    async def fake_run_and_stream(name, args):
        captured_args.append(args)
        list_path = args[args.index("-l") + 1]
        content = Path(list_path).read_text(encoding="utf-8")
        yield {"url": "http://a.target.com", "status_code": 200, "content": content}

    monkeypatch.setattr(scan, "run_and_stream", fake_run_and_stream)
    records = [r async for r in scan.httpx_probe(["a.target.com", "evil.com"], ["*.target.com"])]
    assert len(records) == 1
    assert "a.target.com" in records[0]["content"]
    assert "evil.com" not in records[0]["content"]
    # the temp input file must be cleaned up afterwards
    list_path = captured_args[0][captured_args[0].index("-l") + 1]
    assert not os.path.exists(list_path)


@pytest.mark.asyncio
async def test_httpx_probe_short_circuits_when_everything_is_out_of_scope(monkeypatch):
    called = False

    async def fake_run_and_stream(name, args):
        nonlocal called
        called = True
        yield {}

    monkeypatch.setattr(scan, "run_and_stream", fake_run_and_stream)
    records = [r async for r in scan.httpx_probe(["evil.com"], ["only.allowed.com"])]
    assert records == []
    assert called is False  # never even invoked the tool


@pytest.mark.asyncio
async def test_nuclei_scan_passes_severity_and_include_raw_flags(monkeypatch):
    captured: dict = {}

    async def fake_run_and_stream(name, args):
        captured["args"] = args
        yield {"template-id": "t1", "info": {"severity": "high", "name": "X"}}

    monkeypatch.setattr(scan, "run_and_stream", fake_run_and_stream)
    records = [
        r async for r in scan.nuclei_scan(["https://t.example/x"], severities=["high", "critical"], include_raw=True)
    ]
    assert records == [{"template-id": "t1", "info": {"severity": "high", "name": "X"}}]
    assert "-severity" in captured["args"]
    assert "high,critical" in captured["args"]
    assert "-include-rr" in captured["args"]


@pytest.mark.asyncio
async def test_katana_crawl_refuses_out_of_scope_url():
    with pytest.raises(scope.ScopeError):
        async for _ in scan.katana_crawl("https://evil.com/", ["only.allowed.com"]):
            pass


def test_katana_url_extraction_top_level_and_nested():
    assert scan.katana_url({"url": "https://t/a"}) == "https://t/a"
    assert scan.katana_url({"request": {"endpoint": "https://t/b"}}) == "https://t/b"
    assert scan.katana_url({"request": {"url": "https://t/c"}}) == "https://t/c"
    assert scan.katana_url({}) == ""


# --- CLI dispatch -------------------------------------------------------------


def _recon_ns(**over):
    base = dict(
        subcommand="recon",
        recon_cmd="subfinder",
        domain="target.com",
        scope=None,
        out=None,
        log_file=None,
        log_level=None,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def test_cli_recon_missing_binary_is_usage_not_crash(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    rc = runner.run_cli(_recon_ns())
    assert rc == runner.EXIT_USAGE


def test_cli_recon_subfinder_refused_out_of_scope(tmp_path):
    scopefile = tmp_path / "scope.txt"
    scopefile.write_text("only.allowed.com\n")
    rc = runner.run_cli(_recon_ns(domain="evil.com", scope=str(scopefile)))
    assert rc == runner.EXIT_USAGE


def test_cli_recon_subfinder_writes_out_file(tmp_path, monkeypatch, capsys):
    script = _fake_binary(tmp_path, [json.dumps({"host": "a.target.com"}), json.dumps({"host": "b.target.com"})])
    monkeypatch.setattr("shutil.which", lambda name: str(script))
    out = tmp_path / "subs.jsonl"
    rc = runner.run_cli(_recon_ns(out=str(out)))
    assert rc == runner.EXIT_OK
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["host"] == "a.target.com"
    assert "2 registro(s)" in capsys.readouterr().out


def test_cli_recon_httpx_reports_dropped_out_of_scope(tmp_path, monkeypatch, capsys):
    script = _fake_binary(tmp_path, [json.dumps({"url": "http://a.target.com", "status_code": 200})])
    monkeypatch.setattr("shutil.which", lambda name: str(script))
    list_file = tmp_path / "hosts.txt"
    list_file.write_text("a.target.com\nevil.com\n")
    scopefile = tmp_path / "scope.txt"
    scopefile.write_text("*.target.com\n")
    rc = runner.run_cli(_recon_ns(recon_cmd="httpx", domain=None, list=str(list_file), scope=str(scopefile)))
    assert rc == runner.EXIT_OK
    out = capsys.readouterr().out
    assert "1 host(s) fora do escopo" in out


# --- doctor registers the 4 recon tools ---------------------------------------


def test_doctor_registers_all_recon_tools(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    from curlcommander.cli.onboarding import _gather_checks

    checks = _gather_checks()
    labels = {c.name for c in checks}
    for tool in TOOLS.values():
        assert tool.label in labels
    recon_checks = [c for c in checks if c.name in {t.label for t in TOOLS.values()}]
    assert all(not c.essential for c in recon_checks)  # never blocks the command
    assert all(not c.ok for c in recon_checks)  # nothing on PATH in this test
