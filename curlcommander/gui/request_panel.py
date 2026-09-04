from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Select, TextArea

from curlcommander.config import AUTH_TYPES, BODY_TYPES, HTTP_METHODS
from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig


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
            line = line.strip()
            if ":" in line:
                k, v = line.split(":", 1)
                headers.append(k.strip(), v.strip())

        params = HeaderList()
        for line in self.query_one("#params-area", TextArea).text.splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                params.append(k.strip(), v.strip())

        body_type = self._select_value("body-type-select", "none")
        body = self.query_one("#body-area", TextArea).text
        auth_type = self._select_value("auth-type-select", "none")
        auth_value = self.query_one("#auth-value-input", Input).value

        return RequestConfig(
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            body_type=body_type,
            auth_type=auth_type,
            auth_value=auth_value,
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

    def clear_form(self) -> None:
        self.query_one("#method-select", Select).value = "GET"
        self.query_one("#url-input", Input).value = ""
        self.query_one("#headers-area", TextArea).load_text("")
        self.query_one("#params-area", TextArea).load_text("")
        self.query_one("#body-type-select", Select).value = "none"
        self.query_one("#body-area", TextArea).load_text("")
        self.query_one("#auth-type-select", Select).value = "none"
        self.query_one("#auth-value-input", Input).value = ""

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
