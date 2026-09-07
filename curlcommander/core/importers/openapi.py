"""Manual OpenAPI 3.0 / 3.1 → list[RequestConfig] importer.

Deliberately dependency-light: no ``openapi-core``/``prance``. We walk
``paths`` for operations, ``components.schemas`` for ``$ref`` resolution, and
``components.securitySchemes`` to seed auth. Wherever the spec gives no concrete
example we leave a ``FUZZ`` marker so the request is immediately fuzzable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig

FUZZ = "FUZZ"
_HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


class SpecImportError(ValueError):
    """Raised when a spec cannot be parsed into requests."""


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load a JSON or YAML spec from disk into a dict."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_spec_text(text, str(path))


def parse_spec_text(text: str, source: str = "<spec>") -> dict[str, Any]:
    stripped = text.lstrip()
    try:
        if stripped.startswith("{"):
            data = json.loads(text)
        else:
            import yaml

            data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001 - normalise to our own error
        raise SpecImportError(f"não foi possível ler o spec {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecImportError(f"spec {source} inválido: esperava um objeto no topo")
    return data


def parse_openapi(spec: dict[str, Any]) -> list[RequestConfig]:
    """Turn an OpenAPI 3.x document into one RequestConfig per operation."""
    if "openapi" not in spec or "paths" not in spec:
        raise SpecImportError("documento OpenAPI inválido: faltam as chaves 'openapi' e/ou 'paths'")

    base = _base_url(spec)
    components = spec.get("components") or {}
    schemas = components.get("schemas") or {}
    schemes = components.get("securitySchemes") or {}
    global_security = spec.get("security") or []

    out: list[RequestConfig] = []
    for raw_path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        shared_params = item.get("parameters") or []
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            out.append(
                _operation_to_config(
                    method.upper(),
                    base,
                    str(raw_path),
                    op,
                    shared_params,
                    schemas,
                    schemes,
                    op.get("security", global_security),
                )
            )
    return out


def _base_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers") or []
    if servers and isinstance(servers[0], dict):
        url = str(servers[0].get("url", "")).rstrip("/")
        if url.startswith(("http://", "https://")):
            return url
    return "https://HOST"


def _operation_to_config(
    method: str,
    base: str,
    raw_path: str,
    op: dict[str, Any],
    shared_params: list[Any],
    schemas: dict[str, Any],
    schemes: dict[str, Any],
    security: list[Any],
) -> RequestConfig:
    params_spec = list(shared_params) + list(op.get("parameters") or [])

    path = raw_path
    query = HeaderList()
    headers = HeaderList()
    for p in params_spec:
        if not isinstance(p, dict):
            continue
        loc = p.get("in")
        name = str(p.get("name", ""))
        if not name:
            continue
        value = _param_value(p)
        if loc == "path":
            path = path.replace("{" + name + "}", value)
        elif loc == "query":
            query.append(name, value)
        elif loc == "header":
            headers.append(name, value)

    body, body_type = _request_body(op, schemas)
    auth_type, auth_value = _auth_from_security(security, schemes)

    return RequestConfig(
        method=method,
        url=base + path,
        params=query,
        headers=headers,
        body=body,
        body_type=body_type,
        auth_type=auth_type,
        auth_value=auth_value,
    )


def _param_value(p: dict[str, Any]) -> str:
    if "example" in p:
        return str(p["example"])
    schema = p.get("schema") or {}
    if isinstance(schema, dict):
        if "example" in schema:
            return str(schema["example"])
        if "default" in schema:
            return str(schema["default"])
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return str(enum[0])
    return FUZZ


def _request_body(op: dict[str, Any], schemas: dict[str, Any]) -> tuple[str, str]:
    rb = op.get("requestBody")
    if not isinstance(rb, dict):
        return "", "none"
    content = rb.get("content") or {}
    json_media = content.get("application/json")
    if isinstance(json_media, dict):
        if "example" in json_media:
            return json.dumps(json_media["example"]), "json"
        schema = json_media.get("schema") or {}
        example = _example_from_schema(schema, schemas, set())
        return json.dumps(example), "json"
    if "application/x-www-form-urlencoded" in content:
        return "field=" + FUZZ, "form"
    return "", "none"


def _resolve_ref(ref: str, schemas: dict[str, Any]) -> dict[str, Any]:
    # Only local component refs are supported: "#/components/schemas/Name".
    name = ref.rsplit("/", 1)[-1]
    target = schemas.get(name)
    return target if isinstance(target, dict) else {}


def _example_from_schema(schema: Any, schemas: dict[str, Any], seen: set[str]) -> Any:
    if not isinstance(schema, dict):
        return FUZZ

    ref = schema.get("$ref")
    if isinstance(ref, str):
        if ref in seen:  # break recursive schemas (e.g. a tree node)
            return {}
        seen = seen | {ref}
        return _example_from_schema(_resolve_ref(ref, schemas), schemas, seen)

    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    stype = schema.get("type")
    if stype == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        return {name: _example_from_schema(sub, schemas, seen) for name, sub in props.items()}
    if stype == "array":
        return [_example_from_schema(schema.get("items") or {}, schemas, seen)]
    if stype == "integer":
        return 0
    if stype == "number":
        return 0
    if stype == "boolean":
        return False
    # string / untyped: leave a fuzzable marker.
    return FUZZ


def _auth_from_security(security: list[Any], schemes: dict[str, Any]) -> tuple[str, str]:
    for requirement in security:
        if not isinstance(requirement, dict):
            continue
        for scheme_name in requirement:
            scheme = schemes.get(scheme_name)
            if not isinstance(scheme, dict):
                continue
            stype = scheme.get("type")
            if stype == "http":
                s = str(scheme.get("scheme", "")).lower()
                if s == "bearer":
                    return "bearer", FUZZ
                if s == "basic":
                    return "basic", f"{FUZZ}:{FUZZ}"
            elif stype == "apiKey" and scheme.get("in") == "header":
                return "apikey", f"{scheme.get('name', 'X-API-Key')}: {FUZZ}"
    return "none", ""
