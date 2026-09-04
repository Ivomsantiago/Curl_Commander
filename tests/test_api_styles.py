"""Tests for 2B.6 — GraphQL, SOAP/XML, gRPC-web, streaming."""

import json

import httpx
import pytest
import respx

from curlcommander.core.api_styles import (
    graphql_config,
    graphql_field_names,
    grpc_web_content_type,
    introspection_config,
    introspection_enabled,
    soap_config,
    xml_config,
)
from curlcommander.core.http_client import send, stream_send
from curlcommander.core.request_model import RequestConfig


def test_graphql_config_shape():
    cfg = graphql_config("https://x/graphql", "{ me { id } }", variables='{"a":1}')
    assert cfg.method == "POST"
    assert cfg.headers.get("Content-Type") == "application/json"
    payload = json.loads(cfg.body)
    assert payload["query"] == "{ me { id } }"
    assert payload["variables"] == {"a": 1}


def test_introspection_detection():
    enabled = json.dumps({"data": {"__schema": {"types": [{"name": "User"}, {"name": "__Type"}]}}})
    assert introspection_enabled(enabled)
    assert graphql_field_names(enabled) == ["User", "__Type"]
    assert not introspection_enabled(json.dumps({"errors": [{"message": "disabled"}]}))


def test_soap_and_xml_content_types():
    soap = soap_config("https://x/svc", "<a/>", action="urn:do", wrap_envelope=True)
    assert soap.headers.get("Content-Type").startswith("text/xml")
    assert soap.headers.get("SOAPAction") == "urn:do"
    assert "soap:Envelope" in soap.body

    xml = xml_config("https://x", "<r/>")
    assert xml.headers.get("Content-Type") == "application/xml"


def test_grpc_web_content_type():
    assert grpc_web_content_type() == "application/grpc-web+proto"


@respx.mock
async def test_graphql_introspection_request_sent():
    route = respx.post("https://x/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"__schema": {"types": []}}})
    )
    await send(introspection_config("https://x/graphql"))
    body = json.loads(route.calls.last.request.content)
    assert "__schema" in body["query"]


@respx.mock
async def test_stream_yields_lines():
    respx.get("https://x/stream").mock(
        return_value=httpx.Response(200, text="line1\nline2\nline3", headers={"content-type": "application/x-ndjson"})
    )
    lines: list[str] = []
    result = await stream_send(RequestConfig(method="GET", url="https://x/stream"), lines.append)
    assert lines == ["line1", "line2", "line3"]
    assert result.status_code == 200
    assert result.body == ""  # not buffered
