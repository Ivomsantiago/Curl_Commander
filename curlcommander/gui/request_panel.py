from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Input, Label, Select, TextArea

import os

from curlcommander.config import AUTH_TYPES, BODY_TYPES, HTTP_METHODS
from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import ParseError, parse_header, parse_param
from curlcommander.core.redaction import reveal_text
from curlcommander.core.request_model import RequestConfig


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class RequestPanel(Widget):
    DEFAULT_CSS = """
    RequestPanel {
        width: 2fr;
        border: round $primary;
        padding: 0 1;
        overflow-y: auto;
    }
    RequestPanel Label {
        margin-top: 1;
        color: $text-muted;
    }
    RequestPanel Input {
        margin-bottom: 0;
    }
    RequestPanel TextArea {
        height: 4;
        margin-bottom: 0;
    }
    #method-url-row {
        height: auto;
    }
    #method-select {
        width: 14;
    }
    #url-input {
        width: 1fr;
    }
    #button-row {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    #send-btn {
        margin-right: 1;
    }
    """

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    class RequestReady(Message):
        def __init__(self, config: RequestConfig) -> None:
            super().__init__()
            self.config = config

    class ConfigChanged(Message):
        def __init__(self, config: RequestConfig) -> None:
            super().__init__()
            self.config = config

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with ScrollableContainer():
            yield Label("Method & URL")
            with Horizontal(id="method-url-row"):
                yield Select(
                    [(m, m) for m in HTTP_METHODS],
                    value="GET",
                    id="method-select",
                )
                yield Input(placeholder="https://api.example.com/path", id="url-input")

            yield Label("Headers  (Key: Value — one per line)")
            yield TextArea("", id="headers-area")

            yield Label("Query Params  (key=value — one per line)")
            yield TextArea("", id="params-area")

            yield Label("Body Type")
            yield Select(
                [(bt, bt) for bt in BODY_TYPES],
                value="none",
                id="body-type-select",
            )

            yield Label("Body")
            yield TextArea("", id="body-area")

            yield Label("Auth Type")
            yield Select(
                [(at, at) for at in AUTH_TYPES],
                value="none",
                id="auth-type-select",
            )

            yield Label("Auth Value  (token / user:pass / Header: Value)")
            yield Input(placeholder="", id="auth-value-input")

            yield Label("Options")
            with Horizontal(id="options-row-1"):
                yield Input(placeholder="proxy (http://127.0.0.1:8080)", id="proxy-input")
                yield Input(placeholder="timeout", value="30", id="timeout-input")
                yield Input(placeholder="retries", value="0", id="retries-input")
            with Horizontal(id="options-row-2"):
                yield Checkbox("Verify TLS", value=True, id="verify-checkbox")
                yield Checkbox("Follow redirects", value=True, id="redirects-checkbox")

            with Horizontal(id="button-row"):
                yield Button("Send", id="send-btn", variant="primary")
                yield Button("Curl Only", id="curl-only-btn")

    # ------------------------------------------------------------------
    # Event handlers — propagate config changes to parent
    # ------------------------------------------------------------------

    def on_input_changed(self, _: Input.Changed) -> None:
        self._emit_config_changed()

    def on_text_area_changed(self, _: TextArea.Changed) -> None:
        self._emit_config_changed()

    def on_select_changed(self, _: Select.Changed) -> None:
        self._emit_config_changed()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        config = self.get_config()
        if event.button.id == "send-btn":
            self.post_message(self.RequestReady(config))
        elif event.button.id == "curl-only-btn":
            from curlcommander.core.curl_builder import build_curl
            try:
                curl_cmd = build_curl(config)
                self.app.query_one("CurlPanel").update_curl(curl_cmd)  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self) -> RequestConfig:
        method = self._select_value("method-select", "GET")
        url = self.query_one("#url-input", Input).value

        headers = HeaderList()
        for line in self.query_one("#headers-area", TextArea).text.splitlines():
            try:
                k, v = parse_header(line)
                headers.append(k, v)
            except ParseError:
                continue  # ignore incomplete lines while the user is typing

        params = HeaderList()
        for line in self.query_one("#params-area", TextArea).text.splitlines():
            try:
                k, v = parse_param(line)
                params.append(k, v)
            except ParseError:
                continue

        body_type = self._select_value("body-type-select", "none")
        body = self.query_one("#body-area", TextArea).text
        auth_type = self._select_value("auth-type-select", "none")
        auth_value = self.query_one("#auth-value-input", Input).value

        # Resolve {{VAR}} references from the environment (2.13 env substitution).
        env = dict(os.environ)
        url = reveal_text(url, env)
        body = reveal_text(body, env)
        auth_value = reveal_text(auth_value, env)
        headers = HeaderList([(k, reveal_text(v, env)) for k, v in headers])
        params = HeaderList([(k, reveal_text(v, env)) for k, v in params])

        return RequestConfig(
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            body_type=body_type,
            auth_type=auth_type,
            auth_value=auth_value,
            proxy=self.query_one("#proxy-input", Input).value.strip(),
            max_retries=_to_int(self.query_one("#retries-input", Input).value, 0),
            timeout=_to_float(self.query_one("#timeout-input", Input).value, 30.0),
            verify_ssl=self.query_one("#verify-checkbox", Checkbox).value,
            follow_redirects=self.query_one("#redirects-checkbox", Checkbox).value,
        )

    def set_config(self, config: RequestConfig) -> None:
        if config.method in HTTP_METHODS:
            self.query_one("#method-select", Select).value = config.method
        self.query_one("#url-input", Input).value = config.url

        self.query_one("#headers-area", TextArea).load_text(
            "\n".join(f"{k}: {v}" for k, v in config.headers.items())
        )
        self.query_one("#params-area", TextArea).load_text(
            "\n".join(f"{k}={v}" for k, v in config.params.items())
        )

        if config.body_type in BODY_TYPES:
            self.query_one("#body-type-select", Select).value = config.body_type
        self.query_one("#body-area", TextArea).load_text(config.body)

        if config.auth_type in AUTH_TYPES:
            self.query_one("#auth-type-select", Select).value = config.auth_type
        self.query_one("#auth-value-input", Input).value = config.auth_value

        self.query_one("#proxy-input", Input).value = config.proxy
        self.query_one("#timeout-input", Input).value = str(config.timeout)
        self.query_one("#retries-input", Input).value = str(config.max_retries)
        self.query_one("#verify-checkbox", Checkbox).value = config.verify_ssl
        self.query_one("#redirects-checkbox", Checkbox).value = config.follow_redirects

    def clear_form(self) -> None:
        self.query_one("#method-select", Select).value = "GET"
        self.query_one("#url-input", Input).value = ""
        self.query_one("#headers-area", TextArea).load_text("")
        self.query_one("#params-area", TextArea).load_text("")
        self.query_one("#body-type-select", Select).value = "none"
        self.query_one("#body-area", TextArea).load_text("")
        self.query_one("#auth-type-select", Select).value = "none"
        self.query_one("#auth-value-input", Input).value = ""
        self.query_one("#proxy-input", Input).value = ""
        self.query_one("#timeout-input", Input).value = "30"
        self.query_one("#retries-input", Input).value = "0"
        self.query_one("#verify-checkbox", Checkbox).value = True
        self.query_one("#redirects-checkbox", Checkbox).value = True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_value(self, widget_id: str, default: str) -> str:
        widget = self.query_one(f"#{widget_id}", Select)
        val = widget.value
        return default if val is Select.BLANK else str(val)

    def _emit_config_changed(self) -> None:
        try:
            self.post_message(self.ConfigChanged(self.get_config()))
        except Exception:
            pass
