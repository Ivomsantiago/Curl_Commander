import shlex
from urllib.parse import quote_plus

from curlcommander.config import DEFAULT_TIMEOUT
from curlcommander.core.auth_handler import resolve_auth
from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig


def _num(value: float) -> str:
    """Render a numeric flag value without a trailing .0 when integral."""
    return str(int(value)) if float(value).is_integer() else str(value)


def _encode_params(params: HeaderList) -> str:
    """Encode query pairs preserving order and duplicates (for HPP)."""
    return "&".join(f"{quote_plus(k)}={quote_plus(v)}" for k, v in params)


def build_curl(config: RequestConfig) -> str:
    """Generate a curl command string from a RequestConfig.

    Always includes -L -s -i. Uses shlex.quote on all parts for safe escaping.
    Auth is resolved into headers before building. URL goes last. Header and
    param order and duplicates are preserved exactly.
    """
    resolved = resolve_auth(config)

    parts: list[str] = ["curl"]

    # -L only when redirects are actually followed (1.2).
    if resolved.follow_redirects:
        parts.append("-L")

    parts += ["-s", "-i"]

    if resolved.http2:
        parts.append("--http2")

    if resolved.compressed:
        parts.append("--compressed")

    if resolved.proxy:
        parts += ["-x", resolved.proxy]

    if resolved.max_retries > 0:
        parts += ["--retry", str(resolved.max_retries)]
        if resolved.retry_delay > 0:
            parts += ["--retry-delay", str(resolved.retry_delay)]

    # Reflect the request timeout in the generated command (1.3).
    if resolved.timeout and resolved.timeout != DEFAULT_TIMEOUT:
        parts += ["--max-time", _num(resolved.timeout)]

    if not resolved.verify_ssl:
        parts.append("-k")

    # Basic auth is sent by httpx as an Authorization header, but resolve_auth
    # leaves it out of headers; emit -u so the curl reproduces the request (1.1).
    if resolved.auth_type == "basic" and resolved.auth_value:
        parts += ["-u", resolved.auth_value]

    parts += ["-X", resolved.method]

    effective_headers = HeaderList(resolved.headers)
    if resolved.body_type == "json":
        effective_headers.setdefault("Content-Type", "application/json")
    elif resolved.body_type == "form":
        effective_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    for key, value in effective_headers:
        parts += ["-H", f"{key}: {value}"]

    if resolved.body:
        parts += ["--data-raw", resolved.body]

    if resolved.output_path:
        parts += ["-o", resolved.output_path]

    url = resolved.url
    if resolved.params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{_encode_params(resolved.params)}"

    parts.append(url)

    return " ".join(shlex.quote(p) for p in parts)
