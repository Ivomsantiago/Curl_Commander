"""Recon & Discovery tab (item 9.2) — a Tree view over core.recon.scan's
subfinder -> httpx -> nuclei pipeline, live-updated as each stage streams.

A thin wiring layer over core.recon.scan, same convention as the other panels
(ProxyPanel/IntruderPanel talk to core directly, not cli/runner.py). Missing
external binaries degrade with the same message the CLI's `recon` subcommand
shows (core.recon.tools.ReconToolError), never a raw traceback.

Selecting (Enter/click) a live-URL leaf promotes it to the Repeater, the same
``PromoteToRepeater`` message IntruderPanel already uses.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static, Tree
from textual.widgets.tree import TreeNode

from curlcommander.core import scope
from curlcommander.core.request_model import RequestConfig

_SEVERITY_COLOUR = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan", "INFO": "dim"}


class ReconPanel(Widget):
    DEFAULT_CSS = """
    ReconPanel { height: 1fr; layout: vertical; padding: 0 1; }
    ReconPanel #rp-bar { height: auto; }
    ReconPanel #rp-domain { width: 1fr; }
    ReconPanel #rp-status { height: auto; color: $text-muted; }
    ReconPanel Tree { height: 1fr; }
    """

    class PromoteToRepeater(Message):
        def __init__(self, config: RequestConfig) -> None:
            super().__init__()
            self.config = config

    def compose(self) -> ComposeResult:
        with Horizontal(id="rp-bar"):
            yield Input(placeholder="domínio (ex.: target.com)", id="rp-domain")
            yield Button("Iniciar recon", id="rp-run", variant="primary")
        yield Static("", id="rp-status")
        yield Tree("recon", id="rp-tree")

    def on_mount(self) -> None:
        self.query_one("#rp-tree", Tree).root.expand()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rp-run":
            event.stop()
            self._run()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        url = event.node.data
        if isinstance(url, str) and url:
            self.post_message(self.PromoteToRepeater(RequestConfig(method="GET", url=url)))

    def _status(self, text: str) -> None:
        self.query_one("#rp-status", Static).update(text)

    def _run(self) -> None:
        domain = self.query_one("#rp-domain", Input).value.strip()
        if not domain:
            self._status("[red]Informe um domínio.[/red]")
            return

        scope_entries = getattr(self.app, "scope_entries", []) or []
        if scope_entries:
            try:
                scope.enforce(domain, scope_entries)
            except scope.ScopeError as exc:
                self._status(f"[red bold]Recusado:[/red bold] {exc}")
                return

        tree = self.query_one("#rp-tree", Tree)
        tree.clear()
        tree.root.set_label(domain)
        tree.root.expand()
        self._status("[dim]Enumerando subdomínios…[/dim]")
        self.app.run_worker(self._pipeline(domain, scope_entries), exclusive=True)

    async def _pipeline(self, domain: str, scope_entries: list[str]) -> None:
        from curlcommander.core.recon import scan
        from curlcommander.core.recon.tools import ReconToolError

        tree = self.query_one("#rp-tree", Tree)
        host_nodes: dict[str, TreeNode] = {}
        try:
            async for record in scan.subfinder(domain, scope_entries):
                host = str(record.get("host", "")).strip()
                if not host:
                    continue
                host_nodes[host] = tree.root.add(host, data=None)
        except ReconToolError as exc:
            self._status(f"[yellow]{exc}[/yellow]")
            return
        except scope.ScopeError as exc:
            self._status(f"[red bold]Recusado:[/red bold] {exc}")
            return

        if not host_nodes:
            self._status("[yellow]Nenhum subdomínio encontrado.[/yellow]")
            return

        self._status(f"[dim]{len(host_nodes)} subdomínio(s) — sondando hosts vivos…[/dim]")
        live_urls: dict[str, TreeNode] = {}
        try:
            async for record in scan.httpx_probe(list(host_nodes), scope_entries):
                url = str(record.get("url", ""))
                if not url:
                    continue
                status = record.get("status_code", record.get("status-code", "?"))
                title = record.get("title", "")
                host = str(record.get("host") or url.split("//", 1)[-1].split("/", 1)[0])
                parent = host_nodes.get(host, tree.root)
                live_urls[url] = parent.add_leaf(f"[bold]{status}[/bold] {url}  {title}", data=url)
        except ReconToolError as exc:
            self._status(f"[yellow]{exc}[/yellow]")
            return

        if not live_urls:
            self._status("[yellow]Nenhum host vivo encontrado.[/yellow]")
            return

        self._status(f"[dim]{len(live_urls)} URL(s) viva(s) — rodando templates de vulnerabilidade…[/dim]")
        findings = 0
        try:
            async for record in scan.nuclei_scan(list(live_urls), scope_entries=scope_entries):
                findings += 1
                info = record.get("info", {}) if isinstance(record.get("info"), dict) else {}
                sev = str(info.get("severity", "?")).upper()
                matched = record.get("matched-at", record.get("matched_at", ""))
                name = info.get("name", "")
                colour = _SEVERITY_COLOUR.get(sev, "white")
                parent = live_urls.get(matched, tree.root)
                parent.add_leaf(f"[{colour} bold]{sev}[/{colour} bold] {name}", data=matched)
        except ReconToolError as exc:
            self._status(f"[yellow]{exc}[/yellow]")
            return

        self._status(
            f"[green]Concluído[/green] — {len(host_nodes)} subdomínio(s), {len(live_urls)} vivo(s), "
            f"{findings} achado(s) de vulnerabilidade."
        )
