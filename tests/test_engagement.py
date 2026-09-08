"""Tests for per-engagement data isolation (item 8.1) and its CLI surface."""

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.cli.arg_parser import build_request_parser, build_subcommand_parser
from curlcommander.config import (
    InvalidEngagementName,
    db_path_for,
    engagement_dir,
    engagements_dir,
    list_engagements,
    validate_engagement_name,
)

# --- name validation --------------------------------------------------------


@pytest.mark.parametrize("name", ["cliente-x", "Cliente_2026.09", "a", "ENG1"])
def test_validate_engagement_name_accepts_safe_names(name):
    assert validate_engagement_name(name) == name


@pytest.mark.parametrize(
    "name",
    [
        "../etc",
        "a/b",
        "a\\b",
        "",
        ".hidden",
        "-leading-dash",
        "with space",
        "a" * 64,  # too long
    ],
)
def test_validate_engagement_name_rejects_unsafe_names(name):
    with pytest.raises(InvalidEngagementName):
        validate_engagement_name(name)


# --- db_path_for --------------------------------------------------------


def test_db_path_for_no_engagement_returns_default(tmp_path):
    default = tmp_path / "h.db"
    assert db_path_for(None, default) == default
    assert db_path_for("", default) == default


def test_db_path_for_engagement_is_isolated_next_to_default(tmp_path):
    default = tmp_path / "h.db"
    iso = db_path_for("cliente-x", default)
    assert iso == tmp_path / "engagements" / "cliente-x" / "history.db"
    assert iso != default


def test_db_path_for_two_engagements_never_collide(tmp_path):
    default = tmp_path / "h.db"
    a = db_path_for("cliente-a", default)
    b = db_path_for("cliente-b", default)
    assert a != b


def test_db_path_for_rejects_path_traversal(tmp_path):
    with pytest.raises(InvalidEngagementName):
        db_path_for("../../etc", tmp_path / "h.db")


# --- engagements_dir / engagement_dir / list_engagements (real app_dir) ---


def test_list_engagements_empty_when_none_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    assert list_engagements() == []


def test_list_engagements_finds_only_dirs_with_a_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    real = engagement_dir("real-eng")
    real.mkdir(parents=True)
    (real / "history.db").write_bytes(b"")
    empty = engagements_dir() / "no-db-here"
    empty.mkdir(parents=True)
    assert list_engagements() == ["real-eng"]


# --- end-to-end isolation: two engagements never share data -----------------


def _request_args(**over):
    args = build_request_parser().parse_args([over.pop("url", "https://api.target.com/x")])
    args.subcommand = None
    for k, v in over.items():
        setattr(args, k, v)
    return args


@respx.mock
def test_two_engagements_get_fully_separate_history(tmp_path, monkeypatch):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))

    runner.run_cli(_request_args(engagement="cliente-a"))
    runner.run_cli(_request_args(engagement="cliente-b"))
    runner.run_cli(_request_args(engagement=None))  # ad-hoc, no isolation

    from curlcommander.storage.history_repo import HistoryRepo

    db_a = db_path_for("cliente-a", tmp_path / "h.db")
    db_b = db_path_for("cliente-b", tmp_path / "h.db")
    assert db_a != db_b
    assert db_a.exists() and db_b.exists()

    repo_a = HistoryRepo(db_a)
    repo_b = HistoryRepo(db_b)
    repo_ad_hoc = HistoryRepo(tmp_path / "h.db")
    try:
        assert repo_a.count() == 1
        assert repo_b.count() == 1
        assert repo_ad_hoc.count() == 1
        # cliente-a's isolated DB has ONLY cliente-a's row.
        assert repo_a.load()[0].engagement == "cliente-a"
        assert repo_b.load()[0].engagement == "cliente-b"
    finally:
        repo_a.close()
        repo_b.close()
        repo_ad_hoc.close()


# --- `curlcmd engagement list|delete` CLI ------------------------------------


def _sub_args(argv):
    return build_subcommand_parser().parse_args(argv)


def test_cli_engagement_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    rc = runner.run_cli(_sub_args(["engagement", "list"]))
    assert rc == runner.EXIT_OK
    assert "Nenhum engajamento" in capsys.readouterr().out


@respx.mock
def test_cli_engagement_list_shows_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))

    rc = runner.run_cli(_sub_args(["engagement", "list"]))
    assert rc == runner.EXIT_OK
    out = capsys.readouterr().out
    assert "cliente-x" in out


def test_cli_engagement_delete_missing_is_ok_noop(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    rc = runner.run_cli(_sub_args(["engagement", "delete", "nope", "--yes"]))
    assert rc == runner.EXIT_OK
    assert "não existe" in capsys.readouterr().out


@respx.mock
def test_cli_engagement_delete_with_yes_removes_the_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))
    target = engagement_dir("cliente-x")
    assert target.exists()

    rc = runner.run_cli(_sub_args(["engagement", "delete", "cliente-x", "--yes"]))
    assert rc == runner.EXIT_OK
    assert not target.exists()


@respx.mock
def test_cli_engagement_delete_without_yes_requires_typed_name_match(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))
    target = engagement_dir("cliente-x")

    # Wrong confirmation -> refused, directory untouched.
    monkeypatch.setattr("builtins.input", lambda prompt: "not-the-name")
    rc = runner.run_cli(_sub_args(["engagement", "delete", "cliente-x"]))
    assert rc == runner.EXIT_USAGE
    assert target.exists()
    assert "não confere" in capsys.readouterr().out

    # Correct confirmation -> deleted.
    monkeypatch.setattr("builtins.input", lambda prompt: "cliente-x")
    rc = runner.run_cli(_sub_args(["engagement", "delete", "cliente-x"]))
    assert rc == runner.EXIT_OK
    assert not target.exists()


def test_cli_engagement_delete_rejects_path_traversal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    rc = runner.run_cli(_sub_args(["engagement", "delete", "../../etc", "--yes"]))
    assert rc == runner.EXIT_USAGE
    assert "inválido" in capsys.readouterr().out


# --- history/replay/curl/export/delete/clear respect --engagement ----------


@respx.mock
def test_cli_history_engagement_flag_scopes_to_isolated_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))

    rc = runner.run_cli(_sub_args(["history", "--engagement", "cliente-x"]))
    assert rc == runner.EXIT_OK
    assert "api.target.com" in capsys.readouterr().out

    rc = runner.run_cli(_sub_args(["history"]))  # ad-hoc DB: never saw that request
    assert rc == runner.EXIT_OK
    assert "api.target.com" not in capsys.readouterr().out
