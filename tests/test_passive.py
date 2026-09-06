"""Tests for passive security analysis (2.2)."""

from curlcommander.core.passive import analyze, to_sarif
from curlcommander.core.request_model import ResponseResult


def _resp(headers, body="", url="https://t/x"):
    return ResponseResult(200, "OK", headers, body, "text/html", 1.0, len(body), None), url


def test_missing_security_headers_flagged():
    result, url = _resp({})
    findings = analyze(result, url)
    cats = {f.category for f in findings}
    assert "security-headers" in cats
    titles = " ".join(f.title for f in findings)
    assert "CSP" in titles and "HSTS" in titles


def test_hardened_response_has_no_header_findings():
    result, url = _resp(
        {
            "content-security-policy": "default-src 'self'",
            "strict-transport-security": "max-age=63072000",
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
        }
    )
    findings = analyze(result, url)
    assert not [f for f in findings if f.category == "security-headers"]


def test_cookie_without_flags_flagged():
    result, url = _resp({"set-cookie": "sid=abc; Path=/"})
    findings = analyze(result, url)
    cookie = [f for f in findings if f.category == "cookie-flags"]
    assert cookie and "HttpOnly" in cookie[0].detail and "Secure" in cookie[0].detail


def test_cors_wildcard_with_credentials_is_high():
    result, url = _resp({"access-control-allow-origin": "*", "access-control-allow-credentials": "true"})
    findings = analyze(result, url)
    cors = [f for f in findings if f.category == "cors"]
    assert cors and cors[0].severity == "high"
    assert findings[0].severity == "high"  # most-severe first


def test_verbose_error_flagged():
    result, url = _resp({}, body="... Traceback (most recent call last): ...")
    findings = analyze(result, url)
    assert any(f.category == "verbose-error" for f in findings)


def test_to_sarif_shape():
    result, url = _resp({"set-cookie": "s=1"})
    doc = to_sarif(analyze(result, url), url)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["results"]
    assert all("ruleId" in r and "level" in r for r in doc["runs"][0]["results"])
