"""Helpers for non-REST API styles (2B.6): GraphQL, SOAP/XML, gRPC-web.

These shape a RequestConfig (body + the right Content-Type) so the existing
transport sends them correctly. Streaming/NDJSON/SSE consumption lives in
http_client.stream_send.
"""

from __future__ import annotations

import json

from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig

# Standard GraphQL introspection query (trimmed to schema/type names).
INTROSPECTION_QUERY = (
    "query IntrospectionQuery { __schema { queryType { name } mutationType { name } types { name kind } } }"
)


def graphql_config(
    url: str,
    query: str,
    variables: str | None = None,
    headers: HeaderList | None = None,
) -> RequestConfig:
    payload: dict[str, object] = {"query": query}
    if variables:
        payload["variables"] = json.loads(variables)
    h = HeaderList(headers) if headers else HeaderList()
    h.setdefault("Content-Type", "application/json")
    return RequestConfig(method="POST", url=url, headers=h, body=json.dumps(payload), body_type="json")


def introspection_config(url: str, headers: HeaderList | None = None) -> RequestConfig:
    return graphql_config(url, INTROSPECTION_QUERY, headers=headers)


def introspection_enabled(response_body: str) -> bool:
    """True if a GraphQL introspection response looks enabled (has __schema)."""
    try:
        data = json.loads(response_body)
    except (json.JSONDecodeError, ValueError):
        return False
    return bool(data.get("data", {}).get("__schema"))


def graphql_field_names(response_body: str) -> list[str]:
    """Best-effort enumeration of type names from an introspection response."""
    try:
        data = json.loads(response_body)
    except (json.JSONDecodeError, ValueError):
        return []
    types = data.get("data", {}).get("__schema", {}).get("types", [])
    return [t.get("name", "") for t in types if t.get("name")]


SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\n'
    "  <soap:Body>\n{body}\n  </soap:Body>\n"
    "</soap:Envelope>"
)


def soap_config(
    url: str,
    body: str,
    action: str | None = None,
    wrap_envelope: bool = False,
    headers: HeaderList | None = None,
) -> RequestConfig:
    xml = SOAP_ENVELOPE.format(body=body) if wrap_envelope else body
    h = HeaderList(headers) if headers else HeaderList()
    h.setdefault("Content-Type", "text/xml; charset=utf-8")
    if action is not None:
        h.setdefault("SOAPAction", action)
    return RequestConfig(method="POST", url=url, headers=h, body=xml, body_type="raw")


def xml_config(url: str, body: str, headers: HeaderList | None = None) -> RequestConfig:
    h = HeaderList(headers) if headers else HeaderList()
    h.setdefault("Content-Type", "application/xml")
    return RequestConfig(method="POST", url=url, headers=h, body=body, body_type="raw")


def grpc_web_content_type() -> str:
    return "application/grpc-web+proto"
