from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter
from rich.console import Console

from curlcommander.config import AUTH_TYPES, BODY_TYPES, HTTP_METHODS
from curlcommander.core.headers import HeaderList
from curlcommander.core.parsing import ParseError, parse_header, parse_param
from curlcommander.core.request_model import RequestConfig

_console = Console(stderr=True)


def run_wizard() -> RequestConfig | None:
    """Interactively build a RequestConfig using prompt_toolkit."""
    _console.print("[bold cyan]CurlCommander — Assistente interativo[/bold cyan]")
    _console.print("[dim]Pressione Ctrl+C para cancelar[/dim]\n")

    try:
        method = (
            prompt("Método [GET]: ", completer=WordCompleter(HTTP_METHODS, ignore_case=True)).strip().upper() or "GET"
        )

        url = prompt("URL: ").strip()
        if not url:
            _console.print("[red]A URL é obrigatória.[/red]")
            return None

        _console.print("\n[dim]Cabeçalhos — formato 'Chave: Valor', linha em branco para terminar[/dim]")
        headers = HeaderList()
        while True:
            line = prompt("  Cabeçalho: ").strip()
            if not line:
                break
            try:
                k, v = parse_header(line)
                headers.append(k, v)
            except ParseError:
                _console.print("[yellow]  Use o formato 'Chave: Valor'[/yellow]")

        _console.print("\n[dim]Parâmetros de query — formato 'chave=valor', linha em branco para terminar[/dim]")
        params = HeaderList()
        while True:
            line = prompt("  Parâmetro: ").strip()
            if not line:
                break
            try:
                k, v = parse_param(line)
                params.append(k, v)
            except ParseError:
                _console.print("[yellow]  Use o formato 'chave=valor'[/yellow]")

        body_type = (
            prompt(
                "\nTipo de corpo (none/json/form/raw) [none]: ",
                completer=WordCompleter(BODY_TYPES),
            ).strip()
            or "none"
        )

        body = ""
        if body_type != "none":
            body = prompt(f"Corpo ({body_type}): ").strip()

        auth_type = (
            prompt(
                "\nTipo de auth (none/bearer/basic/apikey) [none]: ",
                completer=WordCompleter(AUTH_TYPES),
            ).strip()
            or "none"
        )

        auth_value = ""
        if auth_type != "none":
            prompts = {
                "bearer": "Token Bearer: ",
                "basic": "usuário:senha: ",
                "apikey": "'Cabeçalho: Valor': ",
            }
            auth_value = prompt(prompts.get(auth_type, "Valor de auth: ")).strip()

        _console.print("\n[dim]Opções[/dim]")
        no_redirect_s = prompt("Desativar redirects? [s/N]: ").strip().lower()
        follow_redirects = no_redirect_s not in ("s", "sim", "y", "yes")

        no_verify_s = prompt("Desativar verificação SSL? [s/N]: ").strip().lower()
        verify_ssl = no_verify_s not in ("s", "sim", "y", "yes")

        timeout_s = prompt("Timeout em segundos [30]: ").strip()
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
