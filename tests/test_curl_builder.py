import shlex

from curlcommander.core.curl_builder import build_curl
from curlcommander.core.request_model import RequestConfig


def _parts(curl_cmd: str) -> list[str]:
    return shlex.split(curl_cmd)


def test_basic_get():
    config = RequestConfig(method="GET", url="https://example.com")
    cmd = build_curl(config)
    parts = _parts(cmd)
    assert parts[:4] == ["curl", "-L", "-s", "-i"]
    assert "-X" in parts
    assert parts[parts.index("-X") + 1] == "GET"
    assert parts[-1] == "https://example.com"


def test_always_includes_flags():
    config = RequestConfig(method="DELETE", url="https://example.com/1")
    cmd = build_curl(config)
    assert "-L" in cmd
    assert "-s" in cmd
    assert "-i" in cmd


def test_no_verify_adds_k():
    config = RequestConfig(method="GET", url="https://example.com", verify_ssl=False)
    cmd = build_curl(config)
    assert "-k" in _parts(cmd)


def test_verify_ssl_no_k():
    config = RequestConfig(method="GET", url="https://example.com", verify_ssl=True)
    cmd = build_curl(config)
    assert "-k" not in _parts(cmd)


def test_post_with_json_body():
    config = RequestConfig(
        method="POST",
        url="https://api.example.com/users",
        body='{"id":1}',
        body_type="json",
    )
    cmd = build_curl(config)
    parts = _parts(cmd)
    assert "-X" in parts and parts[parts.index("-X") + 1] == "POST"
    assert "--data-raw" in parts
    assert parts[parts.index("--data-raw") + 1] == '{"id":1}'
    assert "Content-Type: application/json" in parts


def test_bearer_auth_in_headers():
    config = RequestConfig(
        method="GET",
        url="https://api.example.com",
        auth_type="bearer",
        auth_value="mytoken",
    )
    cmd = build_curl(config)
    parts = _parts(cmd)
    assert "-H" in parts
    h_indices = [i for i, p in enumerate(parts) if p == "-H"]
    header_values = [parts[i + 1] for i in h_indices]
    assert "Authorization: Bearer mytoken" in header_values


def test_apikey_auth_in_headers():
    config = RequestConfig(
        method="GET",
        url="https://api.example.com",
        auth_type="apikey",
        auth_value="X-API-Key: secret",
    )
    cmd = build_curl(config)
    parts = _parts(cmd)
    h_indices = [i for i, p in enumerate(parts) if p == "-H"]
    header_values = [parts[i + 1] for i in h_indices]
    assert "X-API-Key: secret" in header_values


def test_query_params_appended_to_url():
    config = RequestConfig(
        method="GET",
        url="https://example.com/search",
        params={"q": "hello", "page": "1"},
    )
    cmd = build_curl(config)
    url_part = _parts(cmd)[-1]
    assert "q=hello" in url_part
    assert "page=1" in url_part


def test_query_params_with_existing_query_string():
    config = RequestConfig(
        method="GET",
        url="https://example.com/search?existing=true",
        params={"extra": "yes"},
    )
    cmd = build_curl(config)
    url_part = _parts(cmd)[-1]
    assert "existing=true" in url_part
    assert "extra=yes" in url_part
    assert url_part.count("?") == 1


def test_custom_headers():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        headers={"Accept": "application/json", "X-Trace": "abc"},
    )
    cmd = build_curl(config)
    parts = _parts(cmd)
    h_indices = [i for i, p in enumerate(parts) if p == "-H"]
    header_values = [parts[i + 1] for i in h_indices]
    assert "Accept: application/json" in header_values
    assert "X-Trace: abc" in header_values


def test_url_is_last():
    config = RequestConfig(
        method="POST",
        url="https://example.com",
        body="data",
        body_type="raw",
        headers={"X-H": "v"},
    )
    cmd = build_curl(config)
    assert _parts(cmd)[-1] == "https://example.com"


def test_http2_and_compressed_flags():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        compressed=True,
        http2=True,
    )
    cmd = build_curl(config)
    parts = _parts(cmd)
    assert "--compressed" in parts
    assert "--http2" in parts


def test_proxy_and_retry_flags():
    config = RequestConfig(
        method="GET",
        url="https://example.com",
        proxy="http://proxy.local:8080",
        max_retries=3,
        retry_delay=2,
        output_path="out.txt",
    )
    cmd = build_curl(config)
    parts = _parts(cmd)
    assert "-x" in parts
    assert "http://proxy.local:8080" in parts
    assert "--retry" in parts
    assert "3" in parts
    assert "--retry-delay" in parts
    assert "2" in parts
    assert "-o" in parts
    assert "out.txt" in parts


def test_full_example():
    config = RequestConfig(
        method="POST",
        url="https://api.target.com/users",
        body='{"id":1}',
        body_type="json",
        auth_type="bearer",
        auth_value="tok",
    )
    cmd = build_curl(config)
    assert "curl" in cmd
    assert "-X POST" in cmd
    assert "Content-Type: application/json" in cmd
    assert "Authorization: Bearer tok" in cmd
    assert '{"id":1}' in cmd
    assert "https://api.target.com/users" in cmd
