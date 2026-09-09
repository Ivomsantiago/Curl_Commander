"""Tests for core.browser.chromium_executable() — pure path/glob resolution,
no Playwright import needed, so unlike test_browser_xss.py this isn't gated
behind the [browser] extra.

Written after discovering (via a real `playwright install chromium` +
PyInstaller onedir build, item 10.3) that current Playwright ships Chrome
for Testing under `chrome-linux64`/`chrome-win64`/`chrome-mac64`, not the
older `chrome-linux`/`chrome-win`/`chrome-mac` this function only matched —
silently reporting Chromium as absent (`curlcmd doctor`) even though
Playwright's own browser launch succeeded via its own env-var handling.
"""

from curlcommander.core import browser


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_chromium_executable_prefers_explicit_env_override(tmp_path, monkeypatch):
    explicit = _touch(tmp_path / "my-own-chrome")
    monkeypatch.setenv("CURLCOMMANDER_CHROMIUM", str(explicit))
    assert browser.chromium_executable() == str(explicit)


def test_chromium_executable_finds_current_chrome_for_testing_layout(tmp_path, monkeypatch):
    """Current Playwright layout: chromium-<id>/chrome-linux64/chrome."""
    monkeypatch.delenv("CURLCOMMANDER_CHROMIUM", raising=False)
    exe = _touch(tmp_path / "chromium-1234" / "chrome-linux64" / "chrome")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert browser.chromium_executable() == str(exe)


def test_chromium_executable_still_finds_older_layout(tmp_path, monkeypatch):
    """Older Playwright layout (pre Chrome-for-Testing): chrome-linux, no -64."""
    monkeypatch.delenv("CURLCOMMANDER_CHROMIUM", raising=False)
    exe = _touch(tmp_path / "chromium-999" / "chrome-linux" / "chrome")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert browser.chromium_executable() == str(exe)


def test_chromium_executable_finds_mac_app_bundle_layouts(tmp_path, monkeypatch):
    """Playwright macOS layouts: chrome-mac-x64, chrome-mac-arm64, chrome-mac64 with .app bundles."""
    monkeypatch.delenv("CURLCOMMANDER_CHROMIUM", raising=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))

    exe1 = _touch(tmp_path / "chromium-1234" / "chrome-mac-x64" / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing")
    assert browser.chromium_executable() == str(exe1)


def test_chromium_executable_finds_win64_layout(tmp_path, monkeypatch):
    """Playwright Windows layout: chromium-<id>/chrome-win64/chrome.exe."""
    monkeypatch.delenv("CURLCOMMANDER_CHROMIUM", raising=False)
    exe = _touch(tmp_path / "chromium-1234" / "chrome-win64" / "chrome.exe")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert browser.chromium_executable() == str(exe)


def test_chromium_executable_none_when_nothing_matches(tmp_path, monkeypatch):
    monkeypatch.delenv("CURLCOMMANDER_CHROMIUM", raising=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))  # empty dir
    assert browser.chromium_executable() is None


def test_chromium_executable_none_when_neither_env_var_set(monkeypatch):
    monkeypatch.delenv("CURLCOMMANDER_CHROMIUM", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    assert browser.chromium_executable() is None

