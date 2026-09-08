"""Achados (Findings) tab (item 9.3) — a live table over the active
engagement's persisted validation_results, groupable by severity, with a
"Gerar relatório" button that calls core.report and opens the resulting HTML.

A thin wiring layer over core.report/storage.validation_repo, same convention
as the other new tabs: reads the shared engagement from the status bar (9.4)
rather than owning its own copy of that field.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Select, Static

from curlcommander.config import DB_PATH, db_path_for
from curlcommander.core.report import report_severity
from curlcommander.storage.validation_repo import StoredValidation, ValidationRepo

_SEVERITY_LABEL = {"high": "Alta", "medium": "Média", "low": "Baixa", "": "—"}
_VERDICT_COLOUR = {"CONFIRMED": "red", "REFLECTED": "yellow", "NOT_VULNERABLE": "green", "ERROR": "red"}


class FindingsPanel(Widget):
    DEFAULT_CSS = """
    FindingsPanel { height: 1fr; layout: vertical; padding: 0 1; }
    FindingsPanel #fp-bar { height: auto; }
    FindingsPanel #fp-severity { width: 20; }
    FindingsPanel DataTable { height: 1fr; }
    FindingsPanel #fp-status { height: auto; color: $text-muted; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[StoredValidation] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="fp-bar"):
            yield Select(
                [("todas", "all"), ("alta", "high"), ("média", "medium"), ("baixa", "low")],
                value="all",
                id="fp-severity",
                allow_blank=False,
            )
            yield Button("Atualizar", id="fp-refresh")
            yield Button("Gerar relatório", id="fp-report", variant="primary")
        with Vertical():
            yield DataTable(id="fp-table")
            yield Static("", id="fp-status")

    def on_mount(self) -> None:
        table = self.query_one("#fp-table", DataTable)
        table.add_columns("Severidade", "Categoria", "Veredito", "URL", "Detalhe")
        table.cursor_type = "row"
        self.refresh_findings()

    def _db_path(self) -> Path:
        default_db = getattr(self.app, "db_path", DB_PATH)
        engagement = getattr(self.app, "engagement", "") or ""
        return Path(db_path_for(engagement, default_db))

    def refresh_findings(self) -> None:
        engagement = getattr(self.app, "engagement", "") or ""
        status = self.query_one("#fp-status", Static)
        if not engagement:
            self._rows = []
            self.query_one("#fp-table", DataTable).clear()
            status.update("[yellow]Defina um engajamento na barra de status.[/yellow]")
            return

        repo = ValidationRepo(self._db_path())
        try:
            self._rows = repo.load(engagement)
        finally:
            repo.close()
        status.update(f"[dim]{len(self._rows)} achado(s) para[/dim] [bold]{engagement}[/bold]")
        self._render_rows()

    def _render_rows(self) -> None:
        table = self.query_one("#fp-table", DataTable)
        table.clear()
        wanted = str(self.query_one("#fp-severity", Select).value)
        for sv in self._rows:
            r = sv.result
            severity = report_severity(r.category, r.evidence) if r.verdict == "CONFIRMED" else ""
            if wanted != "all" and severity != wanted:
                continue
            colour = _VERDICT_COLOUR.get(r.verdict, "white")
            table.add_row(
                _SEVERITY_LABEL.get(severity, severity),
                r.category,
                f"[{colour} bold]{r.verdict}[/{colour} bold]",
                r.url,
                r.detail,
            )

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "fp-severity":
            self._render_rows()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fp-refresh":
            event.stop()
            self.refresh_findings()
        elif event.button.id == "fp-report":
            event.stop()
            self._generate_report()

    def _generate_report(self) -> None:
        from curlcommander.core.report import build_report
        from curlcommander.storage.history_repo import HistoryRepo

        engagement = getattr(self.app, "engagement", "") or ""
        status = self.query_one("#fp-status", Static)
        if not engagement:
            status.update("[yellow]Defina um engajamento na barra de status.[/yellow]")
            return
        if not self._rows:
            status.update("[yellow]Nenhum achado para gerar relatório.[/yellow]")
            return

        db = self._db_path()
        hrepo = HistoryRepo(db)
        try:
            history = hrepo.load_by_engagement(engagement)
        finally:
            hrepo.close()

        html_doc = build_report(engagement, self._rows, history)
        out = Path.cwd() / f"curlcommander-report-{engagement}.html"
        out.write_text(html_doc, encoding="utf-8", newline="\n")

        opened = ""
        try:
            import webbrowser

            if webbrowser.open(out.as_uri()):
                opened = " (aberto no navegador)"
        except Exception:  # noqa: BLE001 - opening the browser is best-effort
            pass
        status.update(f"[green]Relatório gravado em[/green] [bold]{out}[/bold]{opened}")
