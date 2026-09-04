"""Best-effort clipboard read with no hard dependency.

Tries pyperclip (optional extra) then platform CLIs. Raises ClipboardError
when nothing is available so callers can print a clear message.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


class ClipboardError(RuntimeError):
    pass


def read_clipboard() -> str:
    try:
        import pyperclip  # type: ignore

        return str(pyperclip.paste())
    except Exception:
        pass

    candidates: list[list[str]]
    if sys.platform == "darwin":
        candidates = [["pbpaste"]]
    elif sys.platform == "win32":
        candidates = [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    else:
        candidates = [["xclip", "-selection", "clipboard", "-o"], ["xsel", "-b"], ["wl-paste"]]

    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
            except subprocess.SubprocessError:
                continue

    raise ClipboardError("no clipboard tool available (install pyperclip, or xclip/xsel/wl-paste on Linux)")


def write_clipboard(text: str) -> None:
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        return
    except Exception:
        pass

    candidates: list[list[str]]
    if sys.platform == "darwin":
        candidates = [["pbcopy"]]
    elif sys.platform == "win32":
        candidates = [["clip"]]
    else:
        candidates = [["xclip", "-selection", "clipboard"], ["xsel", "-b", "-i"], ["wl-copy"]]

    for cmd in candidates:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text, text=True, check=True)
                return
            except subprocess.SubprocessError:
                continue

    raise ClipboardError("no clipboard tool available to copy")
