"""Tests for `curlcmd setup`, `doctor` and `self-update` (PT-BR onboarding)."""

from argparse import Namespace

from curlcommander.cli import onboarding
from curlcommander.core import features


def _ns(**kw) -> Namespace:
    base = dict(
        all=False, browser=False, proxy=False, socks=False, clipboard=False, payloads=False, yes=False, fix=False
    )
    base.update(kw)
    return Namespace(**base)


def test_setup_base_bootstrap_is_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    # No feature flag: base bootstrap only, always succeeds, installs nothing.
    called = []
    monkeypatch.setattr(onboarding, "_run", lambda argv: called.append(argv) or True)
    assert onboarding.run_setup(_ns()) == onboarding.EXIT_OK
    assert called == []  # nothing installed without a flag


def test_setup_frozen_refuses_feature(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: True)
    assert onboarding.run_setup(_ns(browser=True)) == onboarding.EXIT_USAGE


def test_setup_installs_missing_feature(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "available", lambda name: False)
    ran = []
    monkeypatch.setattr(onboarding, "_run", lambda argv: ran.append(argv) or True)
    # socks has no post-install step, so a single pip call is enough.
    assert onboarding.run_setup(_ns(socks=True, yes=True)) == onboarding.EXIT_OK
    assert ran and ran[0][:4] == [onboarding.sys.executable, "-m", "pip", "install"]
    assert any("httpx[socks]" in part for part in ran[0])


def test_setup_skips_already_available(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "available", lambda name: True)
    ran = []
    monkeypatch.setattr(onboarding, "_run", lambda argv: ran.append(argv) or True)
    assert onboarding.run_setup(_ns(clipboard=True, yes=True)) == onboarding.EXIT_OK
    assert ran == []  # nothing to install, idempotent


def test_confirm_refuses_on_non_tty(monkeypatch):
    monkeypatch.setattr(onboarding.sys.stdin, "isatty", lambda: False)
    assert onboarding._confirm("go?", assume_yes=False) is False
    assert onboarding._confirm("go?", assume_yes=True) is True


def test_doctor_ok_when_essentials_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    assert onboarding.run_doctor(_ns()) == onboarding.EXIT_OK


def test_doctor_gathers_essential_checks(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    checks = onboarding._gather_checks()
    names = {c.name for c in checks}
    assert "Python 3.11+" in names
    assert "Diretório de dados gravável" in names
    essential = [c for c in checks if c.essential]
    assert all(c.ok for c in essential)  # test env is healthy


def test_self_update_reports_method(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "install_method", lambda: "pipx")
    ran = []
    monkeypatch.setattr(onboarding, "_run", lambda argv: ran.append(argv) or True)
    assert onboarding.run_self_update(_ns(yes=True)) == onboarding.EXIT_OK
    assert ran and ran[0] == ["pipx", "upgrade", "curlcommander"]


def test_self_update_frozen_explains(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: True)
    assert onboarding.run_self_update(_ns()) == onboarding.EXIT_OK


def test_setup_yes_no_flags_installs_everything(monkeypatch):
    # `--yes` with no other flags == `--all --yes` (full non-interactive setup).
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "available", lambda name: False)
    feats: list = []
    payloads: list = []
    monkeypatch.setattr(onboarding, "_install_features", lambda names, yes: feats.append(list(names)) or True)
    monkeypatch.setattr(onboarding, "_sync_payloads", lambda yes: payloads.append(True) or True)
    assert onboarding.run_setup(_ns(yes=True)) == onboarding.EXIT_OK
    assert set(feats[0]) == set(onboarding._FEATURE_FLAGS)
    assert payloads == [True]


def test_setup_interactive_yes_to_all_matches_all(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "available", lambda name: False)
    monkeypatch.setattr(onboarding.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(onboarding, "_ask_yes_no", lambda q, default_yes: True)  # "sim" para tudo
    feats: list = []
    payloads: list = []
    monkeypatch.setattr(onboarding, "_install_features", lambda names, yes: feats.append(list(names)) or True)
    monkeypatch.setattr(onboarding, "_sync_payloads", lambda yes: payloads.append(True) or True)
    assert onboarding.run_setup(_ns()) == onboarding.EXIT_OK
    assert set(feats[0]) == set(onboarding._FEATURE_FLAGS)
    assert payloads == [True]


def test_setup_non_tty_no_flags_is_noop_ok(monkeypatch):
    monkeypatch.setattr(onboarding.sys.stdin, "isatty", lambda: False)
    ran: list = []
    monkeypatch.setattr(onboarding, "_run", lambda argv: ran.append(argv) or True)
    assert onboarding.run_setup(_ns()) == onboarding.EXIT_OK
    assert ran == []  # nothing installed without a TTY or --yes


def test_self_update_cancel_runs_nothing(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "install_method", lambda: "uv tool")
    monkeypatch.setattr(onboarding.sys.stdin, "isatty", lambda: False)  # non-TTY, no --yes
    ran = []
    monkeypatch.setattr(onboarding, "_run", lambda argv: ran.append(argv) or True)
    assert onboarding.run_self_update(_ns(yes=False)) == onboarding.EXIT_OK
    assert ran == []


def test_setup_syncs_payloads(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    calls = []
    monkeypatch.setattr(onboarding, "_sync_payloads", lambda assume_yes: calls.append(assume_yes) or True)
    assert onboarding.run_setup(_ns(payloads=True, yes=True)) == onboarding.EXIT_OK
    assert calls == [True]


def test_sync_payloads_calls_sources(monkeypatch, tmp_path):
    from curlcommander.core import payload_sources

    monkeypatch.setattr(payload_sources, "load_sources", lambda: ["seclists"])
    monkeypatch.setattr(payload_sources, "sync", lambda name: tmp_path / name)
    assert onboarding._sync_payloads(assume_yes=True) is True


def test_doctor_fix_installs_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("CURLCOMMANDER_HOME", str(tmp_path))
    monkeypatch.setattr(features, "is_frozen", lambda: False)
    monkeypatch.setattr(features, "available", lambda name: False)  # every extra missing
    installed = []
    monkeypatch.setattr(
        onboarding, "_install_features", lambda names, assume_yes: installed.append(list(names)) or True
    )
    monkeypatch.setattr(onboarding, "_sync_payloads", lambda assume_yes: True)
    # Essentials still pass in the test env, so doctor exits OK after fixing.
    assert onboarding.run_doctor(_ns(fix=True, yes=True)) == onboarding.EXIT_OK
    assert installed and set(installed[0]) <= set(onboarding._FEATURE_FLAGS)
