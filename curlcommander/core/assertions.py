"""Response assertions for CI and vulnerability-fix validation (2.6).

A small, dependency-free JSONPath subset (dot/bracket access with an optional
``== value`` / ``!= value`` comparison) covers the common cases without pulling
in jsonpath-ng.
"""

from __future__ import annotations

import json
import re
import xml.sax.saxutils as sax
from dataclasses import dataclass

from curlcommander.core.request_model import ResponseResult


@dataclass
class AssertionResult:
    name: str
    passed: bool
    detail: str


@dataclass
class AssertionSpec:
    status: int | None = None
    headers: list[str] | None = None  # "Name: Value"
    body_contains: list[str] | None = None
    jsonpaths: list[str] | None = None  # "$.a.b == 1"
    max_ms: float | None = None

    def is_empty(self) -> bool:
        return not any([self.status, self.headers, self.body_contains, self.jsonpaths, self.max_ms])


# --- minimal JSONPath -----------------------------------------------------

_TOKEN_RE = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]|\['([^']*)'\]|\[\"([^\"]*)\"\]")


def _resolve_path(data: object, path: str) -> object:
    if not path.startswith("$"):
        raise KeyError(path)
    current = data
    for m in _TOKEN_RE.finditer(path[1:]):
        key = m.group(1) or m.group(3) or m.group(4)
        idx = m.group(2)
        if idx is not None:
            current = current[int(idx)]  # type: ignore[index]
        else:
            current = current[key]  # type: ignore[index]
    return current


def _coerce(value: str) -> object:
    v = value.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low == "null":
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def eval_jsonpath(body: str, expr: str) -> AssertionResult:
    op = None
    for candidate in ("==", "!="):
        if candidate in expr:
            path, expected_raw = expr.split(candidate, 1)
            op = candidate
            break
    else:
        path, expected_raw = expr, None

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return AssertionResult(f"jsonpath {expr}", False, "response body is not JSON")

    try:
        actual = _resolve_path(data, path.strip())
    except (KeyError, IndexError, TypeError):
        return AssertionResult(f"jsonpath {expr}", False, f"path not found: {path.strip()}")

    if op is None:
        return AssertionResult(f"jsonpath {expr}", True, f"= {actual!r}")

    expected = _coerce(expected_raw or "")
    if op == "==":
        ok = actual == expected
    else:
        ok = actual != expected
    return AssertionResult(f"jsonpath {expr}", ok, f"actual={actual!r} expected{op}{expected!r}")


# --- assertion evaluation -------------------------------------------------


def run_assertions(result: ResponseResult, spec: AssertionSpec) -> list[AssertionResult]:
    out: list[AssertionResult] = []

    if spec.status is not None:
        out.append(
            AssertionResult(
                f"status == {spec.status}",
                result.status_code == spec.status,
                f"got {result.status_code}",
            )
        )

    for h in spec.headers or []:
        name, _, expected = h.partition(":")
        name, expected = name.strip(), expected.strip()
        actual = result.headers.get(name.lower(), result.headers.get(name))
        if expected:
            out.append(AssertionResult(f"header {name}: {expected}", actual == expected, f"got {actual!r}"))
        else:
            out.append(AssertionResult(f"header {name} present", actual is not None, f"got {actual!r}"))

    for needle in spec.body_contains or []:
        out.append(AssertionResult(f"body contains {needle!r}", needle in result.body, ""))

    for expr in spec.jsonpaths or []:
        out.append(eval_jsonpath(result.body, expr))

    if spec.max_ms is not None:
        out.append(
            AssertionResult(
                f"time <= {spec.max_ms:.0f}ms",
                result.duration_ms <= spec.max_ms,
                f"took {result.duration_ms:.0f}ms",
            )
        )

    return out


# --- reporting ------------------------------------------------------------


def format_report(results: list[AssertionResult], fmt: str, url: str = "") -> str:
    if fmt == "json":
        return json.dumps(
            {
                "url": url,
                "passed": all(r.passed for r in results),
                "assertions": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results],
            },
            indent=2,
        )
    if fmt == "junit":
        failures = sum(1 for r in results if not r.passed)
        cases = []
        for r in results:
            body = "" if r.passed else f"<failure message={sax.quoteattr(r.detail)}></failure>"
            cases.append(f"    <testcase name={sax.quoteattr(r.name)}>{body}</testcase>")
        cases_xml = "\n".join(cases)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<testsuite name="curlcommander" tests="{len(results)}" failures="{failures}">\n'
            f"{cases_xml}\n</testsuite>"
        )
    raise ValueError(f"unknown report format: {fmt}")
