"""Tests for the user plugin system (curlcommander.core.plugins)."""

from curlcommander.core import plugins as plugmod
from curlcommander.core.request_model import RequestConfig, ResponseResult

_GOOD_PLUGIN = """
from curlcommander.core.passive import Finding

def register(reg):
    def passive(result, url):
        if result.status_code == 200:
            return [Finding("low", "custom-passive", "Custom passive", url)]
        return []
    reg.add_passive("custom-passive", passive)

    async def active(config, sender):
        return [Finding("info", "custom-active", "Custom active", config.url)]
    reg.add_active("custom-active", active)
"""

_NO_REGISTER = "x = 1\n"
_BOOM = "def register(reg):\n    raise RuntimeError('boom')\n"


def _resp(status=200):
    return ResponseResult(status, "", {}, "", "", 1.0, 0, None)


def _write(dir_, name, content):
    (dir_ / name).write_text(content, encoding="utf-8")


def test_load_and_run_passive(tmp_path):
    _write(tmp_path, "good.py", _GOOD_PLUGIN)
    reg = plugmod.load_plugins(tmp_path)
    assert "good" in reg.loaded
    findings = plugmod.run_passive_plugins(reg, _resp(200), "https://x/")
    assert findings and findings[0].category == "custom-passive"
    # Non-200 → the plugin returns nothing.
    assert plugmod.run_passive_plugins(reg, _resp(404), "https://x/") == []


async def test_load_and_run_active(tmp_path):
    _write(tmp_path, "good.py", _GOOD_PLUGIN)
    reg = plugmod.load_plugins(tmp_path)

    async def sender(cfg):
        return _resp(200)

    findings = await plugmod.run_active_plugins(reg, RequestConfig(method="GET", url="https://x/"), sender)
    assert findings and findings[0].category == "custom-active"


def test_missing_register_is_an_error_not_a_crash(tmp_path):
    _write(tmp_path, "bad.py", _NO_REGISTER)
    reg = plugmod.load_plugins(tmp_path)
    assert reg.loaded == []
    assert any("register" in e for e in reg.errors)


def test_raising_plugin_is_isolated(tmp_path):
    _write(tmp_path, "boom.py", _BOOM)
    reg = plugmod.load_plugins(tmp_path)
    assert reg.loaded == []
    assert any("boom" in e for e in reg.errors)


def test_underscore_files_skipped(tmp_path):
    _write(tmp_path, "_helper.py", _GOOD_PLUGIN)
    reg = plugmod.load_plugins(tmp_path)
    assert reg.loaded == []


def test_summary_shape(tmp_path):
    _write(tmp_path, "good.py", _GOOD_PLUGIN)
    info = plugmod.summary(plugmod.load_plugins(tmp_path))
    assert info["loaded"] == ["good"]
    assert info["passive_checks"] == ["custom-passive"]
    assert info["active_checks"] == ["custom-active"]


def test_runtime_error_in_check_is_isolated(tmp_path):
    src = (
        "from curlcommander.core.passive import Finding\n"
        "def register(reg):\n"
        "    def passive(result, url):\n"
        "        raise ValueError('kaboom')\n"
        "    reg.add_passive('bad-check', passive)\n"
    )
    _write(tmp_path, "p.py", src)
    reg = plugmod.load_plugins(tmp_path)
    assert plugmod.run_passive_plugins(reg, _resp(200), "https://x/") == []
    assert any("kaboom" in e for e in reg.errors)
