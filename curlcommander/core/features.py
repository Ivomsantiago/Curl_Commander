"""Central registry of optional features and how to enable them (PT-BR).

Every optional capability (browser validators, intercepting proxy, SOCKS
proxy, clipboard) is declared once here, with the import used to detect it and
the pip packages that provide it. When a feature is missing the user gets a
single, actionable Portuguese message — never a stack trace — and `curlcmd
setup` reads the same table to install things.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Feature:
    name: str  # setup flag / doctor key, e.g. "browser"
    label: str  # human PT-BR label
    modules: list[str]  # import names that prove availability
    packages: list[str]  # pip packages that provide it
    post_install: list[str] = field(default_factory=list)  # extra steps (message)


FEATURES: dict[str, Feature] = {
    "browser": Feature(
        name="browser",
        label="validadores em navegador (Playwright)",
        modules=["playwright"],
        packages=["playwright"],
        post_install=["playwright install chromium"],
    ),
    "proxy": Feature(
        name="proxy",
        label="proxy interceptador (mitmproxy)",
        modules=["mitmproxy"],
        packages=["mitmproxy"],
    ),
    "socks": Feature(
        name="socks",
        label="proxy SOCKS",
        modules=["socksio"],
        packages=["httpx[socks]"],
    ),
    "clipboard": Feature(
        name="clipboard",
        label="área de transferência (pyperclip)",
        modules=["pyperclip"],
        packages=["pyperclip"],
    ),
}


class FeatureUnavailable(RuntimeError):
    """Raised when an optional feature is used without its extra installed."""


def available(name: str) -> bool:
    feat = FEATURES.get(name)
    if feat is None:
        return False
    return all(importlib.util.find_spec(m) is not None for m in feat.modules)


def is_frozen() -> bool:
    """True when running from the PyInstaller standalone binary."""
    return bool(getattr(sys, "frozen", False))


def install_method() -> str:
    """Best-effort description of how curlcmd is installed (PT-BR)."""
    if is_frozen():
        return "binário standalone (sem Python/pip)"
    exe = sys.executable.lower().replace("\\", "/")
    if "pipx" in exe:
        return "pipx"
    if "/uv/" in exe or "uv/tools" in exe:
        return "uv tool"
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return "ambiente virtual (venv)"
    return "Python do sistema"


def missing_message(name: str) -> str:
    """The standard PT-BR 'feature needs extra, run this' message."""
    feat = FEATURES.get(name)
    if feat is None:
        return f"Recurso desconhecido: {name}."
    if is_frozen():
        return (
            f"O recurso de {feat.label} não está disponível no binário standalone. "
            f"Instale via Python (pipx install curlcommander) e rode: curlcmd setup --{name}"
        )
    return f"O recurso de {feat.label} precisa do extra. Rode: curlcmd setup --{name}"


def require(name: str) -> None:
    """Raise FeatureUnavailable with the PT-BR message if the feature is absent."""
    if not available(name):
        raise FeatureUnavailable(missing_message(name))


def packages_for(names: list[str]) -> list[str]:
    """The pip packages that provide the given feature names (order preserved)."""
    packages: list[str] = []
    for name in names:
        feat = FEATURES.get(name)
        if feat is None:
            continue
        for pkg in feat.packages:
            if pkg not in packages:
                packages.append(pkg)
    return packages


def post_install_for(names: list[str]) -> list[str]:
    """Extra shell steps (e.g. `playwright install chromium`) for the features."""
    steps: list[str] = []
    for name in names:
        feat = FEATURES.get(name)
        if feat is None:
            continue
        for step in feat.post_install:
            if step not in steps:
                steps.append(step)
    return steps


def pip_install_command(packages: list[str]) -> list[str]:
    """Argv that installs ``packages`` into the running interpreter's environment.

    Uses ``sys.executable -m pip``, which targets the venv (or pipx/uv tool
    venv) that hosts the running curlcmd — so the extras land next to it. The
    caller must check :func:`is_frozen` first (a standalone binary has no pip).
    """
    return [sys.executable, "-m", "pip", "install", "--upgrade", *packages]
