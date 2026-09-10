"""Handlers for reading and maintaining request history."""

import os

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from curlcommander.core.redaction import reveal_text
from curlcommander.storage.history_repo import HistoryRepo

EXIT_OK = 0
EXIT_USAGE = 1


def show_history(repo: HistoryRepo, console: Console, reveal: bool = False) -> int:
    entries = repo.load()
    if not entries:
        console.print("[dim]No history entries.[/dim]")
        return EXIT_OK

    env = dict(os.environ)
    table = Table(title="Request History", show_lines=False)
    table.add_column("ID", style="dim", justify="right")
    table.add_column("Timestamp")
    table.add_column("Method")
    table.add_column("URL", no_wrap=True, max_width=50)
    table.add_column("Status", justify="center")
    table.add_column("ms", justify="right")

    for entry in entries:
        style = status_style(entry.status_code)
        url = reveal_text(entry.request.url, env) if reveal else entry.request.url
        table.add_row(
            str(entry.id),
            entry.timestamp,
            entry.request.method,
            url,
            f"[{style}]{entry.status_code or 'ERR'}[/{style}]",
            f"{entry.duration_ms:.0f}",
        )

    console.print(table)
    return EXIT_OK


def show_curl(repo: HistoryRepo, id: int, console: Console, reveal: bool = False) -> int:
    entry = repo.get_by_id(id)
    if entry is None:
        console.print(f"[red]No history entry with ID {id}.[/red]")
        return EXIT_USAGE

    curl_cmd = reveal_text(entry.curl_cmd, dict(os.environ)) if reveal else entry.curl_cmd
    console.print(Syntax(curl_cmd, "bash", theme="monokai", word_wrap=True))
    return EXIT_OK


def export_history(repo: HistoryRepo, output: str, console: Console, reveal: bool = False) -> int:
    repo.export_json(output, reveal=reveal)
    console.print(f"[green]History exported to[/green] [bold]{output}[/bold]")
    return EXIT_OK


def delete_history(repo: HistoryRepo, id: int, console: Console) -> int:
    entry = repo.get_by_id(id)
    if entry is None:
        console.print(f"[red]No history entry with ID {id}.[/red]")
        return EXIT_USAGE
    repo.delete_by_id(id)
    console.print(f"[green]Deleted history entry {id}.[/green]")
    return EXIT_OK


def status_style(status_code: int | None) -> str:
    if status_code is None:
        return "red"
    if status_code < 300:
        return "green"
    if status_code < 400:
        return "yellow"
    return "red"
