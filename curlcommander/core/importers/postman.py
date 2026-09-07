"""Postman Collection v2.1 → list[RequestConfig] importer.

Walks the (recursively nested) ``item`` tree, resolving ``{{var}}`` templates
against an optional environment (Postman env export or a flat dict). Requests
keep their method, URL, headers, query, body and auth. Anything the collection
leaves as a bare ``{{var}}`` with no environment value stays literal so the
gap is visible rather than silently dropped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from curlcommander.core.headers import HeaderList
from curlcommander.core.importers.openapi import SpecImportError
from curlcommander.core.request_model import RequestConfig

_VAR = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def load_env(path: str | Path) -> dict[str, str]:
    """Load a Postman environment export (or a flat JSON object) into a dict."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("values"), list):
        env: dict[str, str] = {}
        for v in data["values"]:
            if isinstance(v, dict) and v.get("enabled", True) and "key" in v:
                env[str(v["key"])] = str(v.get("value", ""))
        return env
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    raise SpecImportError("ambiente Postman inválido: esperava um objeto ou export com 'values'")


def parse_postman(collection: dict[str, Any], env: dict[str, str] | None = None) -> list[RequestConfig]:
    """Turn a Postman v2.x collection into one RequestConfig per request item."""
    info = collection.get("info")
    if not isinstance(info, dict) or "item" not in collection:
        raise SpecImportError("coleção Postman inválida: faltam 'info' e/ou 'item'")

    env = env or {}
    out: list[RequestConfig] = []
    _walk(collection.get("item") or [], env, out)
    return out


def _walk(items: list[Any], env: dict[str, str], out: list[RequestConfig]) -> None:
    for it in items:
        if not isinstance(it, dict):
            continue
        if isinstance(it.get("item"), list):  # a folder: recurse
            _walk(it["item"], env, out)
        elif isinstance(it.get("request"), dict):
            out.append(_request_to_config(it["request"], env))


def _sub(text: str, env: dict[str, str]) -> str:
    return _VAR.sub(lambda m: env.get(m.group(1), m.group(0)), text)


def _request_to_config(req: dict[str, Any], env: dict[str, str]) -> RequestConfig:
    method = str(req.get("method", "GET")).upper()

    headers = HeaderList()
    for h in req.get("header") or []:
        if isinstance(h, dict) and not h.get("disabled") and "key" in h:
            headers.append(_sub(str(h["key"]), env), _sub(str(h.get("value", "")), env))

    url_raw = req.get("url")
    url, query = _resolve_url(url_raw, env)

    body, body_type = _resolve_body(req.get("body"), env)
    auth_type, auth_value = _resolve_auth(req.get("auth"), env)

    return RequestConfig(
        method=method,
        url=url,
        headers=headers,
        params=query,
        body=body,
        body_type=body_type,
        auth_type=auth_type,
        auth_value=auth_value,
    )


def _resolve_url(url_raw: Any, env: dict[str, str]) -> tuple[str, HeaderList]:
    query = HeaderList()
    if isinstance(url_raw, str):
        return _sub(url_raw, env), query
    if isinstance(url_raw, dict):
        raw = url_raw.get("raw")
        for q in url_raw.get("query") or []:
            if isinstance(q, dict) and not q.get("disabled") and "key" in q:
                query.append(_sub(str(q["key"]), env), _sub(str(q.get("value", "")), env))
        if isinstance(raw, str) and raw:
            # The raw string already carries the query; don't double it.
            return _sub(raw.split("?", 1)[0] if query else raw, env), query
    return "", query


def _resolve_body(body: Any, env: dict[str, str]) -> tuple[str, str]:
    if not isinstance(body, dict):
        return "", "none"
    mode = body.get("mode")
    if mode == "raw":
        return _sub(str(body.get("raw", "")), env), "raw"
    if mode == "urlencoded":
        parts = [
            f"{_sub(str(p['key']), env)}={_sub(str(p.get('value', '')), env)}"
            for p in body.get("urlencoded") or []
            if isinstance(p, dict) and not p.get("disabled") and "key" in p
        ]
        return "&".join(parts), "form"
    return "", "none"


def _resolve_auth(auth: Any, env: dict[str, str]) -> tuple[str, str]:
    if not isinstance(auth, dict):
        return "none", ""
    atype = auth.get("type")
    if atype == "bearer":
        return "bearer", _sub(_first_param(auth.get("bearer"), "token"), env)
    if atype == "basic":
        params = auth.get("basic") or []
        user = _sub(_named(params, "username"), env)
        pw = _sub(_named(params, "password"), env)
        return "basic", f"{user}:{pw}"
    if atype == "apikey":
        params = auth.get("apikey") or []
        key = _sub(_named(params, "key"), env)
        value = _sub(_named(params, "value"), env)
        return "apikey", f"{key}: {value}"
    return "none", ""


def _first_param(params: Any, key: str) -> str:
    if isinstance(params, list):
        return _named(params, key)
    return ""


def _named(params: Any, key: str) -> str:
    if isinstance(params, list):
        for p in params:
            if isinstance(p, dict) and p.get("key") == key:
                return str(p.get("value", ""))
    return ""
