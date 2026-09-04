from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from curlcommander.core.headers import HeaderList, coerce

# Field names whose values are HeaderList instances (ordered/duplicate pairs).
_PAIR_FIELDS = frozenset({"headers", "params"})


@dataclass
class RequestConfig:
    method: str
    url: str
    headers: HeaderList = field(default_factory=HeaderList)
    params: HeaderList = field(default_factory=HeaderList)
    body: str = ""
    body_type: str = "none"   # "json" | "form" | "raw" | "none"
    auth_type: str = "none"   # "none" | "bearer" | "basic" | "apikey"
    auth_value: str = ""      # token | user:pass | "Header: Value"
    proxy: str = ""
    max_retries: int = 0
    retry_delay: float = 0.0
    compressed: bool = False
    http2: bool = False
    output_path: str = ""
    pretty: bool = False
    raw: bool = False         # disable pretty-printing / display formatting
    env_file: str = ""
    follow_redirects: bool = True
    verify_ssl: bool = True
    timeout: float = 30.0

    def __post_init__(self) -> None:
        # Accept dict / list-of-pairs / HeaderList for ergonomics and back-compat.
        self.headers = coerce(self.headers)
        self.params = coerce(self.params)

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Full, JSON-serialisable representation of every field."""
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in _PAIR_FIELDS:
                out[f.name] = value.to_jsonable()
            else:
                out[f.name] = value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequestConfig:
        """Rebuild from :meth:`to_dict`, tolerating missing/extra keys."""
        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        for name, value in data.items():
            if name not in known:
                continue
            if name in _PAIR_FIELDS:
                kwargs[name] = HeaderList.from_jsonable(value)
            else:
                kwargs[name] = value
        return cls(**kwargs)


@dataclass
class ResponseResult:
    status_code: int | None
    reason: str
    headers: dict[str, str]
    body: str
    content_type: str
    duration_ms: float
    size_bytes: int
    error: str | None
    content: bytes = b""
    redirects: list[dict[str, str]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class HistoryEntry:
    id: int
    timestamp: str
    request: RequestConfig
    status_code: int | None
    duration_ms: float
    curl_cmd: str
    response_body: bytes = b""
    response_content_type: str = ""
