"""PyInstaller runtime hook: point Playwright at a Chromium bundled alongside
the frozen binary (item 10.3), when the build actually bundled one.

Bundling is opt-in at BUILD time (see packaging/curlcmd.spec): only a build
whose environment had ``PLAYWRIGHT_BROWSERS_PATH`` set and a real Chromium
installed there (``playwright install chromium``) collects it into the
onedir bundle under a ``pw-browsers`` folder. A binary built without that
step (the "lite" release asset) has no such folder, and this hook is then a
no-op — the standalone binary keeps degrading exactly like the pip install
does (``curlcmd setup --browser`` / "install Playwright" message), never a
raw traceback.

``sys._MEIPASS`` is PyInstaller's own documented way to find the bundle's
base directory in BOTH onefile (a temp extraction dir) and onedir (the
app's own folder) modes, so this hook works unchanged if the build ever
switches between the two.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def bundled_browsers_path(frozen: bool, base_dir: str | Path | None) -> Path | None:
    """The bundled ``pw-browsers`` dir, or None if not frozen / not bundled.

    Checked in more than one place because PyInstaller's onedir layout isn't
    one fixed shape across versions: since PyInstaller 6.0, non-executable
    collected files (COLLECT's ``a.binaries``/``a.datas``/our own
    ``Tree(browsers_path, prefix="pw-browsers")`` in curlcmd.spec) default to
    a ``_internal`` subdirectory, but ``sys._MEIPASS`` and
    ``sys.executable``'s own directory don't consistently agree on which side
    of that split they report across PyInstaller releases. Checking
    ``base_dir``, ``base_dir/_internal`` and the executable's own directory
    covers every layout actually seen without needing to pin an exact
    PyInstaller version.
    """
    if not frozen or not base_dir:
        return None
    candidates = [
        Path(base_dir) / "pw-browsers",
        Path(base_dir) / "_internal" / "pw-browsers",
    ]
    exe_dir = os.path.dirname(sys.executable)
    if exe_dir:
        candidates.append(Path(exe_dir) / "pw-browsers")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def apply() -> None:
    base_dir = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    bundled = bundled_browsers_path(getattr(sys, "frozen", False), base_dir)
    if bundled is not None:
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled))


apply()
