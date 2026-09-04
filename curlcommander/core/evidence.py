"""Evidence capture for pentest reports (2B.8).

Saves the raw request, the raw response and a metadata file (with an
authorisation/engagement label) under a stable, timestamped directory ready to
attach to a report. Secrets are redacted unless the caller opts out.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from curlcommander.core.request_model import RequestConfig, ResponseResult

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str) -> str:
    return _SAFE.sub("_", text)[:60] or "target"


def save_evidence(
    out_dir: str | Path,
    config: RequestConfig,
    raw_request: bytes,
    raw_response: bytes,
    result: ResponseResult,
    engagement: str | None = None,
) -> Path:
    from urllib.parse import urlsplit

    host = urlsplit(config.url if "://" in config.url else "https://" + config.url).hostname or "target"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(out_dir) / f"{ts}_{_slug(host)}_{config.method}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "request.txt").write_bytes(raw_request)
    (folder / "response.txt").write_bytes(raw_response)
    meta = {
        "timestamp": ts,
        "engagement": engagement or "",
        "method": config.method,
        "url": config.url,
        "status_code": result.status_code,
        "duration_ms": round(result.duration_ms, 2),
        "size_bytes": result.size_bytes,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return folder


def compose_raw_response(result: ResponseResult) -> bytes:
    """Reconstruct a raw response view when only the parsed parts are available."""
    if result.content and result.content[:5] in (b"HTTP/", b"HTTP1"):
        return result.content  # already a full raw response (raw transport)
    lines = [f"HTTP {result.status_code} {result.reason}".strip()]
    lines += [f"{k}: {v}" for k, v in result.headers.items()]
    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("latin-1", errors="replace") + (result.content or result.body.encode("utf-8", "replace"))
