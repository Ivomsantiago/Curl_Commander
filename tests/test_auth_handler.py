from curlcommander.core.auth_handler import resolve_auth
from curlcommander.core.request_model import RequestConfig


def test_bearer_injects_authorization_header():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="bearer",
        auth_value="mytoken",
    )
    resolved = resolve_auth(config)
    assert resolved.headers["Authorization"] == "Bearer mytoken"


def test_bearer_does_not_mutate_original():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="bearer",
        auth_value="tok",
    )
    resolve_auth(config)
    assert "Authorization" not in config.headers


def test_apikey_injects_custom_header():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="apikey",
        auth_value="X-API-Key: secret123",
    )
    resolved = resolve_auth(config)
    assert resolved.headers["X-API-Key"] == "secret123"


def test_apikey_trims_whitespace():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="apikey",
        auth_value="  X-Token : abc  ",
    )
    resolved = resolve_auth(config)
    assert "X-Token" in resolved.headers
    assert resolved.headers["X-Token"] == "abc"


def test_basic_auth_does_not_inject_header():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="basic",
        auth_value="user:pass",
    )
    resolved = resolve_auth(config)
    # Basic auth is handled by httpx directly — no Authorization header here
    assert "Authorization" not in resolved.headers


def test_none_auth_leaves_headers_unchanged():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="none",
        headers={"Accept": "application/json"},
    )
    resolved = resolve_auth(config)
    assert list(resolved.headers.keys()) == ["Accept"]


def test_apikey_invalid_format_ignored():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="apikey",
        auth_value="no-colon-here",
    )
    resolved = resolve_auth(config)
    # Nothing injected — no ": " separator found
    assert resolved.headers == {}


def test_bearer_preserves_existing_headers():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        auth_type="bearer",
        auth_value="tok",
        headers={"Accept": "application/json"},
    )
    resolved = resolve_auth(config)
    assert resolved.headers["Accept"] == "application/json"
    assert resolved.headers["Authorization"] == "Bearer tok"
