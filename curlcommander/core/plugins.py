"""User plugin system — extend the scanners without touching the core.

A plugin is a plain ``.py`` file dropped in ``<config>/plugins/`` that defines a
module-level ``register(registry)`` function. It adds passive and/or active
checks that run alongside the built-ins:

    # ~/.config/curlcommander/plugins/my_check.py
    def register(reg):
        def passive(result, url):
            from curlcommander.core.passive import Finding
            if "X-Powered-By" in result.headers:
                return [Finding("low", "custom-powered-by", "X-Powered-By presente", result.headers["X-Powered-By"])]
            return []
        reg.add_passive("x-powered-by", passive)

Plugins are **local code you install yourself** — they run with the tool's
privileges, exactly like a Burp/Caido extension. Only add plugins you trust.
A broken plugin is isolated: its import or a raised exception is caught and
surfaced as a load error, never a crash.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from curlcommander.config import app_dir
from curlcommander.core.passive import Finding
from curlcommander.core.request_model import RequestConfig, ResponseResult

PassiveCheck = Callable[[ResponseResult, str], list[Finding]]
Sender = Callable[[RequestConfig], Awaitable[ResponseResult]]
ActiveCheck = Callable[[RequestConfig, Sender], Awaitable[list[Finding]]]


@dataclass
class Registry:
    """Collects the checks contributed by plugins."""

    passive: list[tuple[str, PassiveCheck]] = field(default_factory=list)
    active: list[tuple[str, ActiveCheck]] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_passive(self, name: str, check: PassiveCheck) -> None:
        self.passive.append((name, check))

    def add_active(self, name: str, check: ActiveCheck) -> None:
        self.active.append((name, check))


def plugins_dir() -> Path:
    d = app_dir() / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_file(path: Path, registry: Registry) -> None:
    spec = importlib.util.spec_from_file_location(f"curlcmd_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        registry.errors.append(f"{path.name}: não foi possível carregar")
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if not callable(register):
            registry.errors.append(f"{path.name}: sem função register(registry)")
            return
        register(registry)
        registry.loaded.append(path.stem)
    except Exception as exc:  # noqa: BLE001 - a bad plugin must not crash the tool
        registry.errors.append(f"{path.name}: {type(exc).__name__}: {exc}")


def load_plugins(directory: Path | None = None) -> Registry:
    """Discover and load every ``*.py`` plugin in ``directory`` (default dir)."""
    directory = directory or plugins_dir()
    registry = Registry()
    if not directory.is_dir():
        return registry
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        _load_file(path, registry)
    return registry


def run_passive_plugins(registry: Registry, result: ResponseResult, url: str) -> list[Finding]:
    """Run every passive plugin check, isolating individual failures."""
    findings: list[Finding] = []
    for name, check in registry.passive:
        try:
            findings.extend(check(result, url) or [])
        except Exception as exc:  # noqa: BLE001
            registry.errors.append(f"passive:{name}: {type(exc).__name__}: {exc}")
    return findings


async def run_active_plugins(registry: Registry, config: RequestConfig, sender: Sender) -> list[Finding]:
    """Run every active plugin check, isolating individual failures."""
    findings: list[Finding] = []
    for name, check in registry.active:
        try:
            findings.extend(await check(config, sender) or [])
        except Exception as exc:  # noqa: BLE001
            registry.errors.append(f"active:{name}: {type(exc).__name__}: {exc}")
    return findings


def summary(registry: Registry) -> dict[str, Any]:
    """A JSON-able description of what loaded (for `plugins list` / the GUI)."""
    return {
        "loaded": registry.loaded,
        "passive_checks": [n for n, _ in registry.passive],
        "active_checks": [n for n, _ in registry.active],
        "errors": registry.errors,
    }
