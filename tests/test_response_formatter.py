import json

from curlcommander.core.response_formatter import format_body, get_lexer


def test_json_pretty_prints():
    body = '{"key":"value","number":42}'
    result = format_body(body, "application/json")
    parsed = json.loads(result)
    assert parsed["key"] == "value"
    assert parsed["number"] == 42
    assert "\n" in result  # indented


def test_json_with_charset():
    body = "[1, 2, 3]"
    result = format_body(body, "application/json; charset=utf-8")
    assert result == "[\n  1,\n  2,\n  3\n]"


def test_invalid_json_returned_as_is():
    body = "not valid json"
    result = format_body(body, "application/json")
    assert result == "not valid json"


def test_plain_text_returned_unchanged():
    body = "just plain text\nwith newlines"
    result = format_body(body, "text/plain")
    assert result == body


def test_html_returned_unchanged():
    body = "<html><body>Hi</body></html>"
    result = format_body(body, "text/html")
    assert result == body


def test_empty_body_json():
    result = format_body("", "application/json")
    assert result == ""


def test_get_lexer_json():
    assert get_lexer("application/json") == "json"
    assert get_lexer("application/json; charset=utf-8") == "json"


def test_get_lexer_html():
    assert get_lexer("text/html") == "html"
    assert get_lexer("text/html; charset=utf-8") == "html"


def test_get_lexer_xml():
    assert get_lexer("application/xml") == "xml"
    assert get_lexer("text/xml") == "xml"


def test_get_lexer_fallback():
    assert get_lexer("text/plain") == "text"
    assert get_lexer("application/octet-stream") == "text"
    assert get_lexer("") == "text"
