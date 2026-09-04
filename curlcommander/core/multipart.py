"""Build multipart/form-data uploads from curl-style -F specs.

Each spec is ``name=value`` (a plain field) or ``name=@path[;type=...][;filename=...]``
(a file part). Upload endpoints are prime AppSec targets, so the filename and
content-type are fully controllable.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from curlcommander.core.headers import HeaderList


class MultipartError(ValueError):
    pass


def parse_form_field(name: str, spec: str) -> tuple[str, object]:
    """Return ("data", value) or ("file", (filename, bytes, content_type))."""
    if not spec.startswith("@"):
        return ("data", spec)

    # File part: @path with optional ;type= and ;filename= attributes.
    segments = spec[1:].split(";")
    path = segments[0]
    content_type: str | None = None
    filename: str | None = None
    for attr in segments[1:]:
        key, _, value = attr.partition("=")
        key = key.strip().lower()
        if key == "type":
            content_type = value.strip()
        elif key == "filename":
            filename = value.strip()

    p = Path(path)
    if not p.exists():
        raise MultipartError(f"form file not found: {path}")
    data = p.read_bytes()
    filename = filename or p.name
    content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return ("file", (filename, data, content_type))


def build_multipart(form: HeaderList) -> tuple[dict[str, str], list[tuple[str, tuple[str, bytes, str]]]]:
    """Split -F specs into httpx ``data`` and ``files`` structures."""
    data: dict[str, str] = {}
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for name, spec in form:
        kind, value = parse_form_field(name, spec)
        if kind == "data":
            data[name] = value  # type: ignore[assignment]
        else:
            files.append((name, value))  # type: ignore[arg-type]
    return data, files
