"""Tests for the active scanner (curlcommander.core.active).

A fake sender inspects each crafted request and returns a tailored response, so
the whole scanner is exercised without network or respx.
"""

from urllib.parse import parse_qsl, urlsplit

from curlcommander.core.active import Injectable, _injectables, _mutate, active_scan
from curlcommander.core.request_model import RequestConfig, ResponseResult


def _resp(body="", status=200, headers=None):
    return ResponseResult(
        status_code=status,
        reason="",
        headers=headers or {},
        body=body,
        content_type="text/html",
        duration_ms=1.0,
        size_bytes=len(body),
        error=None,
    )


def _qval(url, name):
    for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        if k == name:
            return v
    return None


def test_injectables_query_and_form():
    cfg = RequestConfig(method="POST", url="https://x/s?q=1&p=2", body="a=1&b=2", body_type="form")
    inj = _injectables(cfg)
    assert Injectable("query", "q") in inj
    assert Injectable("query", "p") in inj
    assert Injectable("form", "a") in inj
    assert Injectable("form", "b") in inj


def test_injectables_none_without_params():
    assert _injectables(RequestConfig(method="GET", url="https://x/s")) == []


def test_mutate_only_target_param():
    cfg = RequestConfig(method="GET", url="https://x/s?q=1&p=2")
    out = _mutate(cfg, Injectable("query", "q"), "PWN")
    assert _qval(out.url, "q") == "PWN"
    assert _qval(out.url, "p") == "2"


def test_mutate_form_body():
    cfg = RequestConfig(method="POST", url="https://x/s", body="a=1&b=2", body_type="form")
    out = _mutate(cfg, Injectable("form", "b"), "PWN")
    assert dict(parse_qsl(out.body)) == {"a": "1", "b": "PWN"}


async def test_reflected_xss_detected():
    async def sender(cfg):
        return _resp(body=f"echo: {_qval(cfg.url, 'q')}")  # reflects verbatim

    cfg = RequestConfig(method="GET", url="https://x/s?q=hi")
    findings = await active_scan(cfg, sender=sender)
    assert any(f.category == "active-xss" for f in findings)


async def test_encoded_reflection_is_not_flagged_xss():
    async def sender(cfg):
        val = _qval(cfg.url, "q") or ""
        return _resp(body="echo: " + val.replace("<", "&lt;").replace(">", "&gt;"))

    cfg = RequestConfig(method="GET", url="https://x/s?q=hi")
    findings = await active_scan(cfg, sender=sender)
    assert not any(f.category == "active-xss" for f in findings)


async def test_error_based_sqli_detected():
    async def sender(cfg):
        if _qval(cfg.url, "q") == "'":
            return _resp(body="You have an error in your SQL syntax near ''")
        return _resp(body="ok")

    cfg = RequestConfig(method="GET", url="https://x/s?q=1")
    findings = await active_scan(cfg, sender=sender)
    assert any(f.category == "active-sqli" for f in findings)


async def test_ssti_detected():
    async def sender(cfg):
        val = _qval(cfg.url, "q") or ""
        # Emulate a template engine evaluating {{7*7}} → 49, keeping the canary.
        if "{{7*7}}" in val:
            return _resp(body="hello " + val.replace("${{7*7}}", "49").replace("{{7*7}}", "49"))
        return _resp(body="hello")

    cfg = RequestConfig(method="GET", url="https://x/s?q=1")
    findings = await active_scan(cfg, sender=sender)
    assert any(f.category == "active-ssti" for f in findings)


async def test_path_traversal_detected():
    async def sender(cfg):
        if "etc/passwd" in (_qval(cfg.url, "file") or ""):
            return _resp(body="root:x:0:0:root:/root:/bin/bash\n")
        return _resp(body="ok")

    cfg = RequestConfig(method="GET", url="https://x/s?file=a.txt")
    findings = await active_scan(cfg, sender=sender)
    assert any(f.category == "active-traversal" for f in findings)


async def test_open_redirect_detected_only_for_redirect_param():
    async def sender(cfg):
        val = _qval(cfg.url, "next")
        if val and val.startswith("https://curlcommander.example/"):
            return _resp(status=302, headers={"Location": val})
        return _resp(body="ok")

    cfg = RequestConfig(method="GET", url="https://x/s?next=/home")
    findings = await active_scan(cfg, sender=sender)
    assert any(f.category == "active-open-redirect" for f in findings)


def test_injectables_include_params():
    cfg = RequestConfig(method="GET", url="https://x/s", params=[("q", "1"), ("p", "2")])
    inj = _injectables(cfg)
    assert Injectable("param", "q") in inj
    assert Injectable("param", "p") in inj


async def test_active_scan_probes_params_field():
    async def sender(cfg):
        # Reflect the value stored in RequestConfig.params (as send() would send).
        val = dict(cfg.params).get("q", "")
        return _resp(body=f"echo {val}")

    cfg = RequestConfig(method="GET", url="https://x/s", params=[("q", "1")])
    findings = await active_scan(cfg, sender=sender)
    assert any(f.category == "active-xss" for f in findings)


async def test_two_vulnerable_params_both_reported():
    async def sender(cfg):
        # Both q and p reflect their query values verbatim.
        q = _qval(cfg.url, "q") or ""
        p = _qval(cfg.url, "p") or ""
        return _resp(body=f"{q}|{p}")

    cfg = RequestConfig(method="GET", url="https://x/s?q=1&p=2")
    findings = await active_scan(cfg, sender=sender)
    xss = [f for f in findings if f.category == "active-xss"]
    # One finding per vulnerable parameter (dedup keys on detail = param name).
    details = {f.detail for f in xss}
    assert len(details) == 2


async def test_clean_app_has_no_findings():
    async def sender(cfg):
        # Reflects nothing back and never errors.
        return _resp(body="static page")

    cfg = RequestConfig(method="GET", url="https://x/s?q=1&p=2")
    findings = await active_scan(cfg, sender=sender)
    assert findings == []
