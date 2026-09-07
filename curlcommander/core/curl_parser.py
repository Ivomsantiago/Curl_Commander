"""Parse a ``curl`` command line back into a RequestConfig.

The inverse of curl_builder. Targets the "Copy as cURL" strings produced by
browser DevTools and Burp: tokenise the command (honouring single/double
quotes, backslash line continuations and Windows ``^`` continuations), then map
the flags we understand onto a RequestConfig, preserving header/param order and
duplicates.

Chrome/Firefox's "Copy as cURL (cmd)" export on Windows is a special case: it
escapes every value for cmd.exe as ``^"value^"``, escapes any literal quote
nested inside a value (e.g. the ``Sec-CH-UA`` header) as ``^^"``, and escapes
other cmd metacharacters inline (``^%``, ``^&``, ...). None of that ``^`` is
real content — see ``_strip_cmd_carets`` — so it is undone before tokenising,
but only when a conservative signature (``^"`` right after ``curl``/``--url``/
``-H``/``-b``) confirms this is a cmd export and not a bash command that
happens to contain a literal ``^`` inside real quotes.
"""

from __future__ import annotations

import re
import shlex
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import parse_header
from curlcommander.core.request_model import RequestConfig


class CurlParseError(ValueError):
    """Raised when a string is not a parseable curl command."""


# Flags that take a value argument.
_VALUE_FLAGS = {
    "-X",
    "--request",
    "-H",
    "--header",
    "-d",
    "--data",
    "--data-raw",
    "--data-binary",
    "--data-ascii",
    "--data-urlencode",
    "-F",
    "--form",
    "-u",
    "--user",
    "-b",
    "--cookie",
    "-x",
    "--proxy",
    "-A",
    "--user-agent",
    "-e",
    "--referer",
    "--max-time",
    "--connect-timeout",
    "-o",
    "--output",
    "--url",
}
# Boolean flags (no argument).
_BOOL_FLAGS = {
    "-k",
    "--insecure",
    "-L",
    "--location",
    "--compressed",
    "--http2",
    "--http2-prior-knowledge",
    "-s",
    "--silent",
    "-i",
    "--include",
    "-G",
    "--get",
}


# A cmd.exe "Copy as cURL (cmd)" export always wraps the value right after
# these flags in ^"..."; a bash command containing a stray ^ inside real
# quotes will not match this, so the check stays conservative.
_CMD_EXPORT_MARKER = re.compile(r'(?:\bcurl|--url|-H|--header|-b|--cookie)\s+\^"')


def _looks_like_cmd_export(command: str) -> bool:
    return bool(_CMD_EXPORT_MARKER.search(command))


def _strip_cmd_carets(command: str) -> str:
    """Undo cmd.exe caret-escaping from a "Copy as cURL (cmd)" export.

    Order matters: a doubled ``^^"`` (a literal quote nested inside a value,
    e.g. Sec-CH-UA) is turned into a backslash-escaped quote first, so shlex
    later treats it as literal content instead of a token boundary. What is
    left of ``^"`` (the wrapping around the whole value) becomes a plain
    quote, and any remaining lone ``^`` (``^%``, ``^&``, ...) is dropped —
    in this format a caret is never real content, purely a cmd.exe escape.
    """
    command = command.replace('^^"', '\\"')
    command = command.replace('^"', '"')
    return command.replace("^", "")


def _normalise(command: str) -> str:
    if _looks_like_cmd_export(command):
        command = _strip_cmd_carets(command)
        # Continuations (` ^\n`) survive the caret strip as bare newlines.
        return command.replace("\n", " ").strip()
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

    form = HeaderList()
    for spec in forms:
        name, _, value = spec.partition("=")
        form.append(name.strip(), value)

    body = ""
    body_type = "none"
    if data_parts:
        body = "&".join(data_parts) if (data_urlencode or force_get) else "".join(data_parts)
        body_type = "raw"
        if force_get:
            for k, v in parse_qsl(body, keep_blank_values=True):
                params.append(k, v)
            body, body_type = "", "none"

    if method is None:
        has_payload = (body_type != "none" or len(form) > 0) and not force_get
        method = "POST" if has_payload else "GET"

    return RequestConfig(
        method=method.upper(),
        url=url,
        headers=headers,
        params=params,
        form=form,
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
