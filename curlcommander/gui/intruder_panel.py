"""Intruder tab — visual attack positions, 4 named modes, sortable result grid.

Marking a position wraps the selected text in Burp-style ``§…§`` markers; on
run those become the fuzz markers ``core.fuzzer`` understands, and the attack
is driven by ``core.intruder`` (sniper / battering-ram / pitchfork /
cluster-bomb). The grid reuses the engine's anomaly flag.
"""

from __future__ import annotations

import json
import re

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Label, Select, Static, TextArea

from curlcommander.core.fuzzer import FuzzResult, substitute
from curlcommander.core.intruder import ATTACK_MODES, marker_scheme, run_attack
from curlcommander.core.request_model import RequestConfig
from curlcommander.gui import rawreq

_POSITION_RE = re.compile(r"§(.*?)§", re.S)


def apply_markers(text: str, mode: str) -> tuple[str, list[str], int]:
    """Turn ``§x§`` spans into fuzz markers; return (marked_text, originals, n)."""
    spans = list(_POSITION_RE.finditer(text))
    markers = marker_scheme(mode, len(spans))
    originals = [m.group(1) for m in spans]
    out: list[str] = []
    last = 0
    for i, m in enumerate(spans):
        out.append(text[last : m.start()])
        out.append(markers[i])
        last = m.end()
    out.append(text[last:])
    return "".join(out), originals, len(spans)


def parse_wordlists(text: str, n_positions: int, mode: str) -> list[list[str]]:
    """Payload groups (blank-line separated) → one wordlist per position.

    One group is reused for every position (and is the single list sniper /
    battering-ram want); N groups map one-to-one onto N positions.
    """
    groups: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                groups.append(current)
                current = []
            continue
        current.append(line)
    if current:
        groups.append(current)
    if not groups:
        raise ValueError("nenhum payload informado")
    if mode in ("sniper", "battering-ram"):
        return [groups[0]]
    if len(groups) == 1:
        return [groups[0] for _ in range(max(1, n_positions))]
    if len(groups) == n_positions:
        return groups
    raise ValueError(f"{len(groups)} listas de payload para {n_positions} posições")


class IntruderPanel(Widget):
    DEFAULT_CSS = """
    IntruderPanel { height: 1fr; layout: horizontal; }
    IntruderPanel #it-left { width: 1fr; }
    IntruderPanel #it-right { width: 1fr; }
    IntruderPanel #it-request { height: 1fr; }
    IntruderPanel #it-payloads { height: 8; }
    IntruderPanel #it-controls { height: auto; }
    IntruderPanel #it-mode { width: 18; }
    IntruderPanel #it-sort { width: 18; }
    IntruderPanel DataTable { height: 1fr; }
    """

    class PromoteToRepeater(Message):
        def __init__(self, config: RequestConfig) -> None:
            super().__init__()
            self.config = config

    def __init__(self, config: RequestConfig | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._base_url = rawreq.base_url_of(config.url) if config else "https://"
        self._initial = rawreq.config_to_text(config) if config else ""
        self._results: list[FuzzResult] = []
        self._display_order: list[int] = []  # table row -> index into _results
        self._base_config: RequestConfig | None = None
        self._markers: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="it-left"):
            yield Label("Requisição (selecione um trecho e 'Marcar posição')")
            yield TextArea(self._initial, id="it-request")
            with Horizontal(id="it-controls"):
                yield Button("Marcar posição", id="it-mark")
                yield Select([(m, m) for m in ATTACK_MODES], value="sniper", id="it-mode", allow_blank=False)
            yield Label("Payloads (um por linha; linha em branco separa listas)")
            yield TextArea("", id="it-payloads")
            with Horizontal():
                yield Button("Atacar", id="it-run", variant="primary")
                yield Select(
                    [("status", "status"), ("tamanho", "size"), ("tempo", "time"), ("posição", "pos")],
                    value="status",
                    id="it-sort",
                    allow_blank=False,
                )
                yield Button("Exportar JSON", id="it-export")
                yield Button("→ Repeater", id="it-promote")
        with Vertical(id="it-right"):
            yield Static("", id="it-summary")
            yield DataTable(id="it-results")

    def on_mount(self) -> None:
        table = self.query_one("#it-results", DataTable)
        table.add_columns("Payload", "Status", "Tamanho", "ms", "★")
        table.cursor_type = "row"

    def load_request(self, config: RequestConfig) -> None:
        self._base_url = rawreq.base_url_of(config.url)
        self.query_one("#it-request", TextArea).load_text(rawreq.config_to_text(config))

    # -- actions ------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "it-mark":
            event.stop()
            self._mark_selection()
        elif event.button.id == "it-run":
            event.stop()
            self._run()
        elif event.button.id == "it-export":
            event.stop()
            self._export()
        elif event.button.id == "it-promote":
            event.stop()
            self._promote_selected()

    def _mark_selection(self) -> None:
        ta = self.query_one("#it-request", TextArea)
        selected = ta.selected_text
        if selected:
            ta.replace(f"§{selected}§", ta.selection.start, ta.selection.end)

    def _mode(self) -> str:
        return str(self.query_one("#it-mode", Select).value)

    def _run(self) -> None:
        mode = self._mode()
        text = self.query_one("#it-request", TextArea).text
        marked, originals, n = apply_markers(text, mode)
        if n == 0:
            self.query_one("#it-summary", Static).update("[red]Marque ao menos uma posição (§…§).[/red]")
            return
        try:
            wordlists = parse_wordlists(self.query_one("#it-payloads", TextArea).text, n, mode)
            base = rawreq.text_to_config(marked, self._base_url)
        except Exception as exc:  # noqa: BLE001
            self.query_one("#it-summary", Static).update(f"[red]Erro:[/red] {exc}")
            return
        self._base_config = base
        self._markers = marker_scheme(mode, n)
        self.query_one("#it-summary", Static).update(f"[dim]Atacando ({mode}, {n} posição/ões)…[/dim]")
        self.app.run_worker(self._run_worker(base, mode, wordlists, originals), exclusive=True)

    async def _run_worker(self, base, mode, wordlists, originals) -> None:
        try:
            self._results = await run_attack(base, mode, wordlists, originals=originals)
        except Exception as exc:  # noqa: BLE001
            self.query_one("#it-summary", Static).update(f"[red]Falha no ataque:[/red] {exc}")
            return
        anomalies = sum(1 for r in self._results if r.anomaly)
        self.query_one("#it-summary", Static).update(
            f"[b]{len(self._results)}[/b] requisições · [yellow]{anomalies}[/yellow] anomalia(s)"
        )
        self._render_results()

    def _render_results(self) -> None:
        table = self.query_one("#it-results", DataTable)
        table.clear()
        key = str(self.query_one("#it-sort", Select).value)
        rows = list(enumerate(self._results))
        keyfns = {
            "status": lambda p: p[1].status_code or 0,
            "size": lambda p: p[1].size_bytes,
            "time": lambda p: p[1].duration_ms,
            "pos": lambda p: p[0],
        }
        rows.sort(key=keyfns.get(key, keyfns["pos"]))
        self._display_order = [i for i, _ in rows]
        for _, r in rows:
            star = "[bold yellow]★[/bold yellow]" if r.anomaly else ""
            status = f"[red]{r.status_code}[/red]" if r.anomaly else str(r.status_code or "ERR")
            table.add_row(" / ".join(r.payloads), status, str(r.size_bytes), f"{r.duration_ms:.0f}", star)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "it-sort" and self._results:
            self._render_results()

    def _export(self) -> None:
        from pathlib import Path

        if not self._results:
            self.query_one("#it-summary", Static).update("[yellow]Nada para exportar ainda.[/yellow]")
            return
        out = Path("curlcommander-intruder.json")
        payload = [
            {
                "payloads": r.payloads,
                "status": r.status_code,
                "size": r.size_bytes,
                "ms": round(r.duration_ms),
                "anomaly": r.anomaly,
            }
            for r in self._results
        ]
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
        self.query_one("#it-summary", Static).update(f"[green]Exportado para[/green] {out}")

    def _promote_selected(self) -> None:
        if not self._results or self._base_config is None:
            return
        table = self.query_one("#it-results", DataTable)
        idx = table.cursor_row
        if idx is None or idx >= len(self._display_order):
            return
        # Rebuild the concrete request for that row and hand it to the Repeater.
        result = self._results[self._display_order[idx]]
        mapping = dict(zip(self._markers, result.payloads, strict=False))
        config = substitute(self._base_config, mapping)
        self.post_message(self.PromoteToRepeater(config))
