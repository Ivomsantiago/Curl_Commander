import json


def charset_of(content_type: str) -> str | None:
    """Extract the charset from a Content-Type header, if present."""
    for part in content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.strip().lower() == "charset" and value:
            return value.strip().strip('"').strip("'")
    return None


def decode_body(content: bytes, content_type: str) -> str:
    """Decode raw response bytes for display.

    Uses the charset from Content-Type, falls back to UTF-8, and replaces
    undecodable bytes so binary payloads never raise or truncate at a bad byte.
    """
    encoding = charset_of(content_type) or "utf-8"
    try:
        return content.decode(encoding, errors="replace")
    except LookupError:  # unknown/misspelled charset label
        return content.decode("utf-8", errors="replace")


def format_body(body: str, content_type: str) -> str:
    """Return body string formatted for display based on content-type."""
    ct = content_type.lower()

    if "json" in ct:
        try:
            parsed = json.loads(body)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            return body

    return body


def get_lexer(content_type: str) -> str:
    """Return a pygments/rich lexer name for the given content-type."""
    ct = content_type.lower()
    if "json" in ct:
        return "json"
    if "html" in ct:
        return "html"
    if "xml" in ct:
        return "xml"
    return "text"
