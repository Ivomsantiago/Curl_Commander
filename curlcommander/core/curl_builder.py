import shlex
from urllib.parse import quote_plus

from curlcommander.core.auth_handler import resolve_auth
from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig


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

    parts: list[str] = ["curl", "-L", "-s", "-i"]

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

    if not resolved.verify_ssl:
        parts.append("-k")

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
