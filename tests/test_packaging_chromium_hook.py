"""Tests for packaging/rthook_chromium.py (item 10.3) — the pure path-resolution
logic behind the PyInstaller runtime hook that points Playwright at a bundled
Chromium. Loaded by file path since packaging/ isn't an importable package."""

import importlib.util
import sys
from pathlib import Path

_HOOK_PATH = Path(__file__).resolve().parent.parent / "packaging" / "rthook_chromium.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location("rthook_chromium_under_test", _HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    # apply() runs at import time; harmless when not frozen (sys.frozen unset).
    spec.loader.exec_module(module)
    return module


def test_bundled_browsers_path_found_when_frozen_and_present(tmp_path):
    hook = _load_hook_module()
    bundled_dir = tmp_path / "pw-browsers"
    bundled_dir.mkdir()
    assert hook.bundled_browsers_path(True, tmp_path) == bundled_dir


def test_bundled_browsers_path_none_when_not_frozen(tmp_path):
    hook = _load_hook_module()
    (tmp_path / "pw-browsers").mkdir()
    assert hook.bundled_browsers_path(False, tmp_path) is None


def test_bundled_browsers_path_none_when_lite_build_has_no_bundle(tmp_path):
    """The 'lite' release asset never ran `playwright install` at build time,
    so packaging/curlcmd.spec never collected a pw-browsers folder — this
    must degrade to None, never raise, so the rest of core.browser's normal
    "install the extra" messaging still applies."""
    hook = _load_hook_module()
    assert hook.bundled_browsers_path(True, tmp_path) is None


def test_bundled_browsers_path_none_when_no_base_dir():
    hook = _load_hook_module()
    assert hook.bundled_browsers_path(True, None) is None


def test_bundled_browsers_path_found_under_internal_subdir(tmp_path):
    """PyInstaller 6+'s default onedir layout collects non-exe files
    (COLLECT's a.binaries/a.datas/our Tree()) into a `_internal` subdirectory
    -- `_MEIPASS` doesn't consistently agree with that split across
    PyInstaller versions, so this has to be checked explicitly rather than
    assumed away."""
    hook = _load_hook_module()
    bundled_dir = tmp_path / "_internal" / "pw-browsers"
    bundled_dir.mkdir(parents=True)
    assert hook.bundled_browsers_path(True, tmp_path) == bundled_dir


def test_bundled_browsers_path_found_next_to_executable(tmp_path, monkeypatch):
    """Falls back to sys.executable's own directory when the bundle isn't
    under base_dir or base_dir/_internal."""
    hook = _load_hook_module()
    exe_dir = tmp_path / "exe_dir"
    exe_dir.mkdir()
    (exe_dir / "pw-browsers").mkdir()
    monkeypatch.setattr(sys, "executable", str(exe_dir / "curlcmd"))
    other_base = tmp_path / "unrelated_base"
    other_base.mkdir()
    assert hook.bundled_browsers_path(True, other_base) == exe_dir / "pw-browsers"


def test_apply_sets_env_var_when_bundle_present(tmp_path, monkeypatch):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    (tmp_path / "pw-browsers").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    hook = _load_hook_module()
    hook.apply()

    import os
    try:
        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(tmp_path / "pw-browsers")
    finally:
        if "PLAYWRIGHT_BROWSERS_PATH" in os.environ:
            del os.environ["PLAYWRIGHT_BROWSERS_PATH"]


def test_apply_is_a_noop_outside_a_frozen_build(monkeypatch):
    """Never touches the environment for a normal `pip install` run."""
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    hook = _load_hook_module()
    hook.apply()

    import os

    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ
