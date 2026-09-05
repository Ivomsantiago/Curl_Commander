# PyInstaller onefile spec for CurlCommander.
# Build:  pyinstaller packaging/curlcmd.spec
# Output: dist/curlcmd  (dist/curlcmd.exe on Windows)

import os

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

entry = os.path.join(SPECPATH, "..", "curlcommander", "__main__.py")
rthook = os.path.join(SPECPATH, "rthook_certs.py")

a = Analysis(
    [entry],
    pathex=[os.path.join(SPECPATH, "..")],
    binaries=tx_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[rthook],
    excludes=["tkinter", "pytest", "_pytest", "mypy", "ruff"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
