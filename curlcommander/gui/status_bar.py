"""Persistent status bar (item 9.4) — one place to set the active engagement,
scope file and auth-macro session for every tab, instead of each tab (Validar,
Recon, Achados) carrying its own copy of the same three fields.

Mirrors the CLI's ``--config`` unification (item 8.4) for the GUI: apply once
here, every panel reads ``self.app.engagement`` / ``.scope_entries`` /
``.auth_macro`` from then on.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Button, Input, Static


class StatusBar(Widget):
    DEFAULT_CSS = """
    StatusBar { dock: bottom; height: auto; border-top: solid $panel; }
    StatusBar #sb-row { height: auto; }
    StatusBar Input { width: 1fr; }
    StatusBar #sb-summary { width: auto; height: auto; padding: 0 1; color: $text-muted; }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="sb-row"):
            yield Input(placeholder="engajamento", id="sb-engagement")
            yield Input(placeholder="arquivo de escopo (opcional)", id="sb-scope")
            yield Input(placeholder="macro de login (opcional)", id="sb-auth-macro")
            yield Button("Aplicar", id="sb-apply", variant="primary")
        yield Static(self._summary("", 0, None), id="sb-summary")

    def apply(self) -> None:
        """Load the three fields into the app's shared session state."""
        from curlcommander.core import scope as scope_mod
        from curlcommander.core.auth_macro import AuthMacro, AuthMacroError

        app = self.app
        engagement = self.query_one("#sb-engagement", Input).value.strip()
        scope_path = self.query_one("#sb-scope", Input).value.strip()
        auth_path = self.query_one("#sb-auth-macro", Input).value.strip()

        app.engagement = engagement  # type: ignore[attr-defined]

        scope_entries: list[str] = []
        if scope_path:
            try:
                scope_entries = scope_mod.load_scope(scope_path)
            except Exception as exc:  # noqa: BLE001
                self._set_summary(f"[red]Escopo inválido:[/red] {exc}")
                return
        app.scope_entries = scope_entries  # type: ignore[attr-defined]

        auth_macro = None
        if auth_path:
            try:
                auth_macro = AuthMacro.from_file(auth_path)
            except AuthMacroError as exc:
                self._set_summary(f"[red]Macro de login inválida:[/red] {exc}")
                return
        app.auth_macro = auth_macro  # type: ignore[attr-defined]

        self._set_summary(self._summary(engagement, len(scope_entries), auth_macro))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sb-apply":
            event.stop()
            self.apply()

    def _set_summary(self, text: str) -> None:
        self.query_one("#sb-summary", Static).update(text)

    @staticmethod
    def _summary(engagement: str, scope_count: int, auth_macro: object) -> str:
        eng = f"[bold]{engagement}[/bold]" if engagement else "[dim](nenhum)[/dim]"
        scope_s = f"{scope_count} host(s) em escopo" if scope_count else "sem escopo (nenhuma restrição)"
        auth_s = "[green]ativo[/green]" if auth_macro is not None else "[dim]nenhum[/dim]"
        return f"engajamento: {eng}  ·  {scope_s}  ·  auth macro: {auth_s}"
