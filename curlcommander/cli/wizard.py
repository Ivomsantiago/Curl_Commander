from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from rich.console import Console

from curlcommander.config import AUTH_TYPES, BODY_TYPES, HTTP_METHODS
from curlcommander.core.headers import HeaderList
from curlcommander.core.request_model import RequestConfig

_console = Console(stderr=True)


def run_wizard() -> RequestConfig | None:
    """Interactively build a RequestConfig using prompt_toolkit."""
    _console.print("[bold cyan]CurlCommander — Interactive Wizard[/bold cyan]")
    _console.print("[dim]Press Ctrl+C to cancel[/dim]\n")

    try:
        method = (
            prompt("Method [GET]: ", completer=WordCompleter(HTTP_METHODS, ignore_case=True)).strip().upper()
            or "GET"
        )

        url = prompt("URL: ").strip()
        if not url:
            _console.print("[red]URL is required.[/red]")
            return None

        _console.print("\n[dim]Headers — format 'Key: Value', blank line to finish[/dim]")
        headers = HeaderList()
        while True:
            line = prompt("  Header: ").strip()
            if not line:
                break
            if ":" in line:
                k, v = line.split(":", 1)
                headers.append(k.strip(), v.strip())
            else:
                _console.print("[yellow]  Use format 'Key: Value'[/yellow]")

        _console.print("\n[dim]Query params — format 'key=value', blank line to finish[/dim]")
        params = HeaderList()
        while True:
            line = prompt("  Param: ").strip()
            if not line:
                break
            if "=" in line:
                k, v = line.split("=", 1)
                params.append(k.strip(), v.strip())
            else:
                _console.print("[yellow]  Use format 'key=value'[/yellow]")

        body_type = (
            prompt(
                "\nBody type (none/json/form/raw) [none]: ",
                completer=WordCompleter(BODY_TYPES),
            ).strip()
            or "none"
        )

        body = ""
        if body_type != "none":
            body = prompt(f"Body ({body_type}): ").strip()

        auth_type = (
            prompt(
                "\nAuth type (none/bearer/basic/apikey) [none]: ",
                completer=WordCompleter(AUTH_TYPES),
            ).strip()
            or "none"
        )

        auth_value = ""
        if auth_type != "none":
            prompts = {
                "bearer": "Bearer token: ",
                "basic": "user:password: ",
                "apikey": "'Header: Value': ",
            }
            auth_value = prompt(prompts.get(auth_type, "Auth value: ")).strip()

        _console.print("\n[dim]Options[/dim]")
        no_redirect_s = prompt("Disable redirects? [y/N]: ").strip().lower()
        follow_redirects = no_redirect_s not in ("y", "yes")

        no_verify_s = prompt("Disable SSL verification? [y/N]: ").strip().lower()
        verify_ssl = no_verify_s not in ("y", "yes")

        timeout_s = prompt("Timeout seconds [30]: ").strip()
        timeout = float(timeout_s) if timeout_s else 30.0

        return RequestConfig(
            method=method,
            url=url,
            headers=headers,
            params=params,
            body=body,
            body_type=body_type,
            auth_type=auth_type,
            auth_value=auth_value,
            follow_redirects=follow_redirects,
            verify_ssl=verify_ssl,
            timeout=timeout,
        )

    except (KeyboardInterrupt, EOFError):
        _console.print("\n[yellow]Cancelled.[/yellow]")
        return None
