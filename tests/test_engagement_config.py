"""Tests for the single engagement config file (item 8.4): one ``--config``
instead of repeating ``--engagement``/``--scope``/``--auth-macro``/``--proxy``
on every subcommand.
"""

import httpx
import pytest
import respx

from curlcommander.cli import runner
from curlcommander.cli.arg_parser import build_request_parser, build_subcommand_parser
from curlcommander.core.engagement_config import (
    EngagementConfig,
    EngagementConfigError,
    apply_defaults,
    load_engagement_config,
)

# --- load_engagement_config ---------------------------------------------


def test_load_engagement_config_happy_path(tmp_path):
    toml = tmp_path / "eng.toml"
    toml.write_text(
        """
        [engagement]
        name = "cliente-x"
        scope_file = "scope.txt"
        auth_macro = "login.yaml"
        proxy = "http://127.0.0.1:8080"

        [wordlists]
        default_source = "seclists"
        """,
        encoding="utf-8",
    )
    cfg = load_engagement_config(toml)
    assert cfg == EngagementConfig(
        name="cliente-x",
        scope_file="scope.txt",
        auth_macro="login.yaml",
        proxy="http://127.0.0.1:8080",
        wordlist_source="seclists",
    )


def test_load_engagement_config_missing_tables_default_to_empty(tmp_path):
    toml = tmp_path / "eng.toml"
    toml.write_text("# no [engagement] or [wordlists] tables\n", encoding="utf-8")
    assert load_engagement_config(toml) == EngagementConfig()


def test_load_engagement_config_missing_file_raises(tmp_path):
    with pytest.raises(EngagementConfigError, match="não foi possível ler"):
        load_engagement_config(tmp_path / "does-not-exist.toml")


def test_load_engagement_config_malformed_toml_raises(tmp_path):
    toml = tmp_path / "bad.toml"
    toml.write_text("this is not [ valid toml =", encoding="utf-8")
    with pytest.raises(EngagementConfigError, match="inválida"):
        load_engagement_config(toml)


def test_load_engagement_config_wrong_table_type_raises(tmp_path):
    toml = tmp_path / "bad.toml"
    toml.write_text('engagement = "not a table"\n', encoding="utf-8")
    with pytest.raises(EngagementConfigError, match="devem ser tabelas TOML"):
        load_engagement_config(toml)


# --- apply_defaults -------------------------------------------------------


def test_apply_defaults_fills_unset_attrs():
    class Args:
        engagement = None
        scope = None
        auth_macro = None
        proxy = None

    args = Args()
    cfg = EngagementConfig(name="cliente-x", scope_file="scope.txt", auth_macro="login.yaml", proxy="http://p:8080")
    apply_defaults(args, cfg)
    assert args.engagement == "cliente-x"
    assert args.scope == "scope.txt"
    assert args.auth_macro == "login.yaml"
    assert args.proxy == "http://p:8080"


def test_apply_defaults_never_overwrites_explicit_cli_value():
    class Args:
        engagement = "cliente-cli"
        scope = None
        auth_macro = None
        proxy = None

    args = Args()
    apply_defaults(args, EngagementConfig(name="cliente-from-file"))
    assert args.engagement == "cliente-cli"  # CLI value wins, file value discarded


def test_apply_defaults_ignores_missing_target_attrs():
    class Args:
        pass

    args = Args()
    apply_defaults(args, EngagementConfig(name="cliente-x"))
    assert args.engagement == "cliente-x"  # type: ignore[attr-defined]


# --- CLI wiring: --config on real subcommands ------------------------------


def _sub_args(argv):
    return build_subcommand_parser().parse_args(argv)


def _request_args(**over):
    args = build_request_parser().parse_args([over.pop("url", "https://api.target.com/x")])
    args.subcommand = None
    for k, v in over.items():
        setattr(args, k, v)
    return args


@respx.mock
def test_cli_config_fills_engagement_for_history(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))

    toml = tmp_path / "eng.toml"
    toml.write_text('[engagement]\nname = "cliente-x"\n', encoding="utf-8")

    rc = runner.run_cli(_sub_args(["history", "--config", str(toml)]))
    assert rc == runner.EXIT_OK
    assert "api.target.com" in capsys.readouterr().out


@respx.mock
def test_cli_explicit_engagement_flag_wins_over_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))
    runner.run_cli(_request_args(engagement="cliente-y"))

    # Config file points at cliente-y, but an explicit --engagement cliente-x
    # on the command line must win.
    toml = tmp_path / "eng.toml"
    toml.write_text('[engagement]\nname = "cliente-y"\n', encoding="utf-8")

    rc = runner.run_cli(_sub_args(["history", "--config", str(toml), "--engagement", "cliente-x"]))
    assert rc == runner.EXIT_OK
    out = capsys.readouterr().out
    assert "api.target.com" in out


def test_cli_config_missing_file_reports_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    rc = runner.run_cli(_sub_args(["history", "--config", str(tmp_path / "nope.toml")]))
    assert rc == runner.EXIT_USAGE
    assert "não foi possível ler" in capsys.readouterr().out


def test_cli_config_malformed_toml_reports_usage_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    toml = tmp_path / "bad.toml"
    toml.write_text("not [ valid =", encoding="utf-8")
    rc = runner.run_cli(_sub_args(["history", "--config", str(toml)]))
    assert rc == runner.EXIT_USAGE
    assert "inválida" in capsys.readouterr().out


@respx.mock
def test_cli_report_resolves_engagement_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(runner, "DB_PATH", tmp_path / "h.db")
    respx.get("https://api.target.com/x").mock(return_value=httpx.Response(200, text="ok"))
    runner.run_cli(_request_args(engagement="cliente-x"))

    toml = tmp_path / "eng.toml"
    toml.write_text('[engagement]\nname = "cliente-x"\n', encoding="utf-8")
    out_html = tmp_path / "report.html"

    rc = runner.run_cli(_sub_args(["report", "--config", str(toml), "--out", str(out_html)]))
    assert rc == runner.EXIT_OK
    assert out_html.exists()


def test_cli_report_without_engagement_or_config_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    rc = runner.run_cli(_sub_args(["report", "--out", str(tmp_path / "r.html")]))
    assert rc == runner.EXIT_USAGE
    assert "--engagement" in capsys.readouterr().out
