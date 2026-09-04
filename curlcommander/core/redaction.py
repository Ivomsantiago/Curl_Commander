"""Secret redaction for anything that gets persisted or exported.

The history DB and its JSON export previously stored the full curl command and
config verbatim --- ``Authorization: Bearer <token>``, ``-u user:pass``, API
keys and cookies in clear text, in a world-readable file. This module strips
those before storage. Two-tier by design:

* If a secret value was supplied through ``--env-file``, it is stored as a
  resolvable reference ``{{VAR}}`` --- recoverable at replay/``--reveal`` time
  from the environment, never as the literal.
* Otherwise the secret is replaced with ``REDACTED`` and is genuinely gone
  from disk. Replay then fails loudly rather than sending an empty credential.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig

REDACTED = "«REDACTED»"

# Header names whose values are secrets and must be masked.
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "apikey",
        "x-auth-token",
        "x-amz-security-token",
        "authentication",
        "x-csrf-token",
    }
)

_REFERENCE_RE = re.compile(r"\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}")


def _reverse_env(env_vars: dict[str, str]) -> list[tuple[str, str]]:
    """Longest values first so we replace maximal secrets before substrings."""
    pairs = [(v, k) for k, v in env_vars.items() if v]
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def _referenceize(value: str, reverse_env: list[tuple[str, str]]) -> str:
    """Replace known env-var secret values with their ``{{VAR}}`` reference."""
    for secret, name in reverse_env:
        if secret and secret in value:
            value = value.replace(secret, f"{{{{{name}}}}}")
    return value


def _mask_value(value: str, reverse_env: list[tuple[str, str]]) -> str:
    """Reference what we can, redact whatever secret remains.

    A leading scheme token (``Bearer``, ``Basic``, ``Digest`` ...) is preserved
    so the auth *type* is still visible after masking.
    """
    if not value:
        return value
    referenced = _referenceize(value, reverse_env)
    if referenced != value:
        # Everything secret became a reference -> safe to keep as-is.
        if not _looks_secret(referenced):
            return referenced
        value = referenced
    if _REFERENCE_RE.fullmatch(value.strip()):
        return value
    scheme_match = re.match(r"([A-Za-z][A-Za-z0-9\-]*)\s+(.+)", value, re.DOTALL)
    if scheme_match and scheme_match.group(1).lower() in {"bearer", "basic", "digest", "negotiate", "token"}:
        return f"{scheme_match.group(1)} {REDACTED}"
    return REDACTED


def _looks_secret(value: str) -> bool:
    """True if the value still contains material outside {{VAR}} references."""
    stripped = _REFERENCE_RE.sub("", value)
    return bool(stripped.strip(" \t:;=,"))


def _redact_proxy(proxy: str, reverse_env: list[tuple[str, str]]) -> str:
    if not proxy or "@" not in proxy:
        return _referenceize(proxy, reverse_env)
    try:
        parts = urlsplit(proxy)
    except ValueError:
        return REDACTED
    if parts.username is None and parts.password is None:
        return proxy
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    netloc = f"{user}:{REDACTED}@{host}" if user else f"{REDACTED}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def redact_headers(headers: HeaderList, reverse_env: list[tuple[str, str]]) -> HeaderList:
    out = HeaderList()
    for key, value in headers:
        if key.lower() in SENSITIVE_HEADERS:
            out.append(key, _mask_value(value, reverse_env))
        else:
            out.append(key, _referenceize(value, reverse_env))
    return out


def redact_config(config: RequestConfig, env_vars: dict[str, str] | None = None) -> RequestConfig:
    """Return a copy of *config* with every secret referenced or redacted."""
    reverse_env = _reverse_env(env_vars or {})
    clone = RequestConfig.from_dict(config.to_dict())

    clone.headers = redact_headers(config.headers, reverse_env)

    if config.auth_type in {"bearer", "basic"} and config.auth_value:
        ref = _referenceize(config.auth_value, reverse_env)
        # Keep the value only if it is now entirely {{VAR}} references.
        clone.auth_value = ref if not _looks_secret(ref) else REDACTED
    elif config.auth_type == "apikey" and config.auth_value:
        # Format is "Header: Value" -- keep the header name, mask the value.
        if ":" in config.auth_value:
            name, val = config.auth_value.split(":", 1)
            clone.auth_value = f"{name}: {_mask_value(val.strip(), reverse_env)}"
        else:
            clone.auth_value = REDACTED

    clone.proxy = _redact_proxy(config.proxy, reverse_env)
    return clone


def reveal_text(text: str, env: dict[str, str]) -> str:
    """Resolve ``{{VAR}}`` references from *env* (used by --reveal)."""
    def repl(match: re.Match[str]) -> str:
        name = match.group(0).strip("{} \t")
        return env.get(name, match.group(0))

    return _REFERENCE_RE.sub(repl, text)


def reveal_config(config: RequestConfig, env: dict[str, str]) -> RequestConfig:
    """Resolve every ``{{VAR}}`` reference in a stored config from *env*."""
    clone = RequestConfig.from_dict(config.to_dict())
    clone.url = reveal_text(config.url, env)
    clone.body = reveal_text(config.body, env)
    clone.auth_value = reveal_text(config.auth_value, env)
    clone.proxy = reveal_text(config.proxy, env)
    clone.headers = HeaderList([(k, reveal_text(v, env)) for k, v in config.headers])
    clone.params = HeaderList([(k, reveal_text(v, env)) for k, v in config.params])
    return clone


def has_redacted(config: RequestConfig) -> bool:
    """True if any credential in the config is an unrecoverable REDACTED mask."""
    fields = [config.auth_value, config.proxy, config.url, config.body]
    fields += [v for _, v in config.headers]
    fields += [v for _, v in config.params]
    return any(REDACTED in (f or "") for f in fields)
