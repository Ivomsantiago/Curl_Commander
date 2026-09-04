import httpx
import respx

from curlcommander.core.http_client import send
from curlcommander.core.request_model import RequestConfig


@respx.mock
async def test_successful_get():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="Hello", headers={"content-type": "text/plain"})
    )
    config = RequestConfig(method="GET", url="https://example.com/")
    result = await send(config)

    assert result.status_code == 200
    assert result.body == "Hello"
    assert result.error is None
    assert result.size_bytes > 0
    assert result.duration_ms >= 0


@respx.mock
async def test_post_with_json():
    respx.post("https://api.example.com/items").mock(
        return_value=httpx.Response(
            201,
            json={"id": 42},
            headers={"content-type": "application/json"},
        )
    )
    config = RequestConfig(
        method="POST",
        url="https://api.example.com/items",
        body='{"name":"test"}',
        body_type="json",
    )
    result = await send(config)

    assert result.status_code == 201
    assert "42" in result.body
    assert result.error is None


@respx.mock
async def test_404_response():
    respx.get("https://example.com/missing").mock(return_value=httpx.Response(404, text="Not Found"))
    config = RequestConfig(method="GET", url="https://example.com/missing")
    result = await send(config)

    assert result.status_code == 404
    assert result.error is None


@respx.mock
async def test_network_error_sets_error_field():
    respx.get("https://example.com/fail").mock(side_effect=httpx.ConnectError("Connection refused"))
    config = RequestConfig(method="GET", url="https://example.com/fail")
    result = await send(config)

    assert result.status_code is None
    assert result.error is not None
    assert "Connection refused" in result.error
    assert result.body == ""


@respx.mock
async def test_bearer_auth_forwarded():
    route = respx.get("https://secure.example.com/data").mock(return_value=httpx.Response(200, text="ok"))
    config = RequestConfig(
        method="GET",
        url="https://secure.example.com/data",
        auth_type="bearer",
        auth_value="supersecret",
    )
    await send(config)

    sent_request = route.calls.last.request
    assert sent_request.headers["authorization"] == "Bearer supersecret"


@respx.mock
async def test_query_params_in_request():
    route = respx.get("https://example.com/search").mock(return_value=httpx.Response(200, text="results"))
    config = RequestConfig(
        method="GET",
        url="https://example.com/search",
        params={"q": "python", "page": "2"},
    )
    await send(config)

    sent_url = str(route.calls.last.request.url)
    assert "q=python" in sent_url
    assert "page=2" in sent_url
