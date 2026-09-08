# PyInstaller spec for CurlCommander.
# Build:  pyinstaller packaging/curlcmd.spec
#
# Two shapes, chosen automatically by the build environment — never a
# separate spec file to keep in sync:
#
# - "lite" (default): PLAYWRIGHT_BROWSERS_PATH unset, or set but nothing
#   installed there. Builds exactly as before: onefile, dist/curlcmd
#   (dist/curlcmd.exe on Windows). Browser validators degrade with the usual
#   "install the extra" message — unchanged behaviour, unchanged shape, so
#   nothing about the existing standalone-binary docs/flow breaks.
# - "full" (item 10.3, opt-in): set PLAYWRIGHT_BROWSERS_PATH and run
#   `playwright install chromium` into it before invoking PyInstaller (see
#   .github/workflows/release.yml). This spec then collects that Chromium
#   into the bundle under pw-browsers/, and switches to onedir —
#   dist/curlcmd/curlcmd — because onefile would have to re-extract a
#   100+ MB browser on every single run. packaging/rthook_chromium.py points
#   Playwright at the bundled copy at startup.

import os

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

# Bundle the package data files (curlcommander/data/payloads/*.txt) and certs.
datas = collect_data_files("curlcommander")
datas += collect_data_files("certifi")

# Hidden imports PyInstaller's static analysis tends to miss.
hiddenimports = collect_submodules("httpx") + collect_submodules("rich") + ["certifi"]

# Textual ships templates/CSS and a large widget tree — collect everything.
tx_datas, tx_binaries, tx_hidden = collect_all("textual")
datas += tx_datas
hiddenimports += tx_hidden

# Optional Chromium bundle (10.3) — only when the build environment actually
# installed one at this exact path. Tree() yields TOC-format (dest, src,
# typecode) triples, valid for COLLECT() but NOT for Analysis(binaries=...)
# (which wants plain (src, dest) pairs) — added after EXE/COLLECT below,
# never mixed into tx_binaries here.
browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
bundle_chromium = bool(browsers_path and os.path.isdir(browsers_path))

entry = os.path.join(SPECPATH, "..", "curlcommander", "__main__.py")
rthook_certs = os.path.join(SPECPATH, "rthook_certs.py")
rthook_chromium = os.path.join(SPECPATH, "rthook_chromium.py")

a = Analysis(
    [entry],
    pathex=[os.path.join(SPECPATH, "..")],
    binaries=tx_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[rthook_certs, rthook_chromium],
    excludes=["tkinter", "pytest", "_pytest", "mypy", "ruff"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if bundle_chromium:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="curlcmd",
        debug=False,
        bootloader_ignore_signals=False,
        strip=os.name != "nt",
        upx=False,
        console=True,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        Tree(browsers_path, prefix="pw-browsers"),
        strip=os.name != "nt",
        upx=False,
        name="curlcmd",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="curlcmd",
        debug=False,
        bootloader_ignore_signals=False,
        strip=os.name != "nt",  # strip symbols where supported (not on Windows)
        upx=False,
        console=True,
        disable_windowed_traceback=False,
    )
