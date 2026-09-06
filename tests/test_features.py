"""Tests for the central optional-feature registry (PT-BR messages)."""

import pytest

from curlcommander.core import features


def test_registry_has_expected_features():
    assert {"browser", "proxy", "socks", "clipboard"} <= set(features.FEATURES)
    assert features.FEATURES["browser"].packages == ["playwright"]
    assert "chromium" in " ".join(features.FEATURES["browser"].post_install)


def test_available_matches_import(monkeypatch):
    # A feature whose module is importable is available; a bogus one is not.
    assert features.available("clipboard") == (
        __import__("importlib.util", fromlist=["util"]).find_spec("pyperclip") is not None
    )
    assert features.available("does-not-exist") is False


def test_missing_message_is_portuguese_and_actionable():
    msg = features.missing_message("proxy")
    assert "precisa do extra" in msg
    assert "curlcmd setup --proxy" in msg


def test_missing_message_frozen(monkeypatch):
    monkeypatch.setattr(features, "is_frozen", lambda: True)
    msg = features.missing_message("browser")
    assert "binário standalone" in msg
    assert "curlcmd setup --browser" in msg


def test_require_raises_when_absent(monkeypatch):
    monkeypatch.setattr(features, "available", lambda name: False)
    with pytest.raises(features.FeatureUnavailable) as exc:
        features.require("browser")
    assert "curlcmd setup --browser" in str(exc.value)


def test_install_method_returns_something():
    assert isinstance(features.install_method(), str)
    assert features.install_method()


def test_browser_require_uses_pt_message(monkeypatch):
    from curlcommander.core import browser

    monkeypatch.setattr(browser, "browser_available", lambda: False)
    with pytest.raises(browser.BrowserError) as exc:
        browser.require_browser()
    assert "curlcmd setup --browser" in str(exc.value)
