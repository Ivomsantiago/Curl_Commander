import base64
import urllib.parse
import html
import binascii

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Select, TextArea
from textual.widget import Widget

class DecoderPanel(Widget):
    """Panel for encoding and decoding data (Base64, URL, Hex, HTML)."""

    DEFAULT_CSS = """
    DecoderPanel {
        height: 1fr;
    }
    DecoderPanel #dc-toolbar {
        height: auto;
        padding-bottom: 1;
    }
    DecoderPanel #dc-input {
        height: 1fr;
        border: solid $accent;
    }
    DecoderPanel #dc-output {
        height: 1fr;
        border: solid $success;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Decoder / Encoder")
        
        with Horizontal(id="dc-toolbar"):
            yield Select(
                [
                    ("Base64", "base64"),
                    ("URL Encode", "url"),
                    ("Hex", "hex"),
                    ("HTML Entities", "html"),
                ],
                prompt="Formato",
                value="base64",
                id="dc-format",
                allow_blank=False,
            )
            yield Button("Encode", id="dc-encode", variant="primary")
            yield Button("Decode", id="dc-decode", variant="warning")
            yield Button("Limpar", id="dc-clear")

        yield TextArea("", id="dc-input", placeholder="Texto de entrada...")
        yield TextArea("", id="dc-output", placeholder="Resultado...", read_only=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dc-clear":
            self.query_one("#dc-input", TextArea).text = ""
            self.query_one("#dc-output", TextArea).text = ""
            return

        fmt = self.query_one("#dc-format", Select).value
        text_in = self.query_one("#dc-input", TextArea).text
        output = self.query_one("#dc-output", TextArea)
        
        if not text_in:
            output.text = ""
            return
            
        try:
            if event.button.id == "dc-encode":
                if fmt == "base64":
                    output.text = base64.b64encode(text_in.encode("utf-8")).decode("utf-8")
                elif fmt == "url":
                    output.text = urllib.parse.quote_plus(text_in)
                elif fmt == "hex":
                    output.text = binascii.hexlify(text_in.encode("utf-8")).decode("utf-8")
                elif fmt == "html":
                    output.text = html.escape(text_in)
            
            elif event.button.id == "dc-decode":
                if fmt == "base64":
                    output.text = base64.b64decode(text_in).decode("utf-8", errors="replace")
                elif fmt == "url":
                    output.text = urllib.parse.unquote_plus(text_in)
                elif fmt == "hex":
                    output.text = binascii.unhexlify(text_in.strip()).decode("utf-8", errors="replace")
                elif fmt == "html":
                    output.text = html.unescape(text_in)
        except Exception as e:
            output.text = f"[Erro na operação: {e}]"
