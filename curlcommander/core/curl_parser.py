"""Parse a ``curl`` command line back into a RequestConfig.

The inverse of curl_builder. Targets the "Copy as cURL" strings produced by
browser DevTools and Burp: tokenise the command (honouring single/double
quotes, backslash line continuations and Windows ``^`` continuations), then map
the flags we understand onto a RequestConfig, preserving header/param order and
duplicates.
"""

from __future__ import annotations

import shlex
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import parse_header
from curlcommander.core.request_model import RequestConfig


class CurlParseError(ValueError):
    """Raised when a string is not a parseable curl command."""


# Flags that take a value argument.
_VALUE_FLAGS = {
    "-X", "--request",
    "-H", "--header",
    "-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--data-urlencode",
    "-F", "--form",
    "-u", "--user",
    "-b", "--cookie",
    "-x", "--proxy",
    "-A", "--user-agent",
    "-e", "--referer",
    "--max-time", "--connect-timeout",
    "-o", "--output",
    "--url",
}
# Boolean flags (no argument).
_BOOL_FLAGS = {
    "-k", "--insecure",
    "-L", "--location",
    "--compressed",
    "--http2", "--http2-prior-knowledge",
    "-s", "--silent",
    "-i", "--include",
    "-G", "--get",
}


def _normalise(command: str) -> str:
    # Join backslash (POSIX) and caret (Windows) line continuations.
    command = command.replace("\\\n", " ").replace("^\n", " ")
    return command.strip()


def tokenize(command: str) -> list[str]:
    command = _normalise(command)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise CurlParseError(f"could not tokenize curl command: {exc}") from exc
    if not tokens:
        raise CurlParseError("empty curl command")
    if tokens[0] != "curl":
        raise CurlParseError("command does not start with 'curl'")
    return tokens


def parse_curl(command: str) -> RequestConfig:
    tokens = tokenize(command)[1:]

    method: str | None = None
    url = ""
    headers = HeaderList()
    params = HeaderList()
    data_parts: list[str] = []
    data_urlencode = False
    forms: list[str] = []
    auth_type = "none"
    auth_value = ""
    proxy = ""
    verify_ssl = True
    follow_redirects = False
    compressed = False
    http2 = False
    output_path = ""
    timeout = 30.0
    force_get = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # Support --flag=value form.
        value: str | None = None
        if tok.startswith("--") and "=" in tok:
            tok, value = tok.split("=", 1)

        if tok in _VALUE_FLAGS:
            if value is None:
                i += 1
                if i >= len(tokens):
                    raise CurlParseError(f"flag {tok} expects a value")
                value = tokens[i]
            if tok in ("-X", "--request"):
                method = value
            elif tok in ("-H", "--header"):
                try:
                    k, v = parse_header(value)
                    headers.append(k, v)
                except ValueError:
                    pass
            elif tok in ("-u", "--user"):
                auth_type, auth_value = "basic", value
            elif tok in ("-b", "--cookie"):
                headers.append("Cookie", value)
            elif tok in ("-x", "--proxy"):
                proxy = value
            elif tok in ("-A", "--user-agent"):
                headers.append("User-Agent", value)
            elif tok in ("-e", "--referer"):
                headers.append("Referer", value)
            elif tok in ("--max-time", "--connect-timeout"):
                try:
                    timeout = float(value)
                except ValueError:
                    pass
            elif tok in ("-o", "--output"):
                output_path = value
            elif tok in ("-F", "--form"):
                forms.append(value)
            elif tok == "--data-urlencode":
                data_urlencode = True
                data_parts.append(value)
            elif tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
                data_parts.append(value.lstrip("@") if tok == "--data-binary" else value)
            elif tok == "--url":
                url = value
        elif tok in _BOOL_FLAGS:
            if tok in ("-k", "--insecure"):
                verify_ssl = False
            elif tok in ("-L", "--location"):
                follow_redirects = True
            elif tok == "--compressed":
                compressed = True
            elif tok in ("--http2", "--http2-prior-knowledge"):
                http2 = True
            elif tok in ("-G", "--get"):
                force_get = True
            # -s / -i are display-only in curl; ignored here.
        elif tok.startswith("-"):
            # Unknown flag: skip; if the next token isn't a flag, skip it too.
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                i += 1
        else:
            url = tok  # positional URL
        i += 1

    if not url:
        raise CurlParseError("no URL found in curl command")

    # Split any query string already on the URL into params (preserving order).
    split = urlsplit(url)
    if split.query:
        for k, v in parse_qsl(split.query, keep_blank_values=True):
            params.append(k, v)
        url = urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))

    body = ""
    body_type = "none"
    if forms:
        body = "&".join(forms)  # placeholder; multipart handled by uploader
        body_type = "form"
    elif data_parts:
        body = "&".join(data_parts) if (data_urlencode or force_get) else "".join(data_parts)
        body_type = "raw"
        if force_get:
            for k, v in parse_qsl(body, keep_blank_values=True):
                params.append(k, v)
            body, body_type = "", "none"

    if method is None:
        method = "GET" if (body_type == "none" or force_get) else "POST"

    return RequestConfig(
        method=method.upper(),
        url=url,
        headers=headers,
        params=params,
        body=body,
        body_type=body_type,
        auth_type=auth_type,
        auth_value=auth_value,
        proxy=proxy,
        compressed=compressed,
        http2=http2,
        output_path=output_path,
        follow_redirects=follow_redirects,
        verify_ssl=verify_ssl,
        timeout=timeout,
    )
