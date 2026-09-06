"""`curlcmd setup`, `curlcmd doctor` and `curlcmd self-update` (PT-BR).

These commands make the optional extras (navegador, proxy, SOCKS, área de
transferência) and the payload sources installable and diagnosable without the
user having to know pip/pipx/uv incantations. Every message is in Portuguese
and carries the concrete corrective action; nothing is installed or downloaded
silently — the plan is shown first and confirmed (or `--yes`/`-y` in scripts).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from curlcommander.core import features

_console = Console()

EXIT_OK = 0
EXIT_USAGE = 1

# The optional features a user can ask setup to install, in a stable order.
_FEATURE_FLAGS = ("browser", "proxy", "socks", "clipboard")


def _selected_features(args) -> list[str]:
    """Features chosen on the command line (``--all`` selects every one)."""
    if getattr(args, "all", False):
        return list(_FEATURE_FLAGS)
    return [name for name in _FEATURE_FLAGS if getattr(args, name, False)]


def _confirm(prompt: str, assume_yes: bool) -> bool:
    """Ask for confirmation unless ``--yes``; refuse silently on a non-TTY."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        _console.print(
            "[red]Recusado:[/red] esta ação precisa de confirmação. "
            "Em scripts/CI rode novamente com [bold]--yes[/bold] (ou -y)."
        )
        return False
    try:
        answer = input(f"{prompt} [s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        _console.print("\n[dim]cancelado[/dim]")
        return False
    return answer in ("s", "sim", "y", "yes")


def _run(argv: list[str]) -> bool:
    """Run a command, streaming its output; return True on success."""
    _console.print(f"[dim]$ {' '.join(argv)}[/dim]")
    try:
        result = subprocess.run(argv, check=False)
    except FileNotFoundError:
        _console.print(f"[red]Erro:[/red] executável não encontrado: [bold]{argv[0]}[/bold]")
        return False
    if result.returncode != 0:
        _console.print(f"[red]Falhou[/red] (código {result.returncode}): {' '.join(argv)}")
        return False
    return True


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


def _ask_yes_no(question: str, default_yes: bool) -> bool:
    """Interactive yes/no with a default; the default answer on empty input."""
    suffix = "[S/n]" if default_yes else "[s/N]"
    try:
        answer = input(f"{question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default_yes
    if not answer:
        return default_yes
    return answer in ("s", "sim", "y", "yes")


def _interactive_select() -> tuple[list[str], bool]:
    """Ask, group by group, what to install (payloads default yes; rest ask)."""
    _console.print("\n[bold]Vamos preparar o curlcmd.[/bold] Responda o que deseja habilitar:")
    want_payloads = _ask_yes_no("Baixar as wordlists de payloads (SecLists etc.)?", default_yes=True)
    selected: list[str] = []
    for name in _FEATURE_FLAGS:
        feat = features.FEATURES[name]
        if features.available(name):
            continue  # already installed — don't ask
        if _ask_yes_no(f"Instalar {feat.label}?", default_yes=False):
            selected.append(name)
    return selected, want_payloads


def run_setup(args) -> int:
    """`curlcmd setup [--all|--browser|--proxy|--socks|--clipboard] [--payloads] [--yes]`.

    Sem flags e num terminal interativo, pergunta grupo a grupo o que instalar
    (payloads = sim por padrão; o resto = pergunta). ``--yes`` sem outras flags
    equivale a ``--all --yes`` (setup completo não-interativo).
    """
    assume_yes = getattr(args, "yes", False)
    all_flag = getattr(args, "all", False)
    selected = _selected_features(args)
    want_payloads = getattr(args, "payloads", False) or all_flag

    # `--yes` sem nenhuma seleção explícita == `--all --yes`.
    if assume_yes and not selected and not all_flag and not getattr(args, "payloads", False):
        all_flag = True
    if all_flag:
        selected = [n for n in _FEATURE_FLAGS if not features.is_frozen()]
        want_payloads = True

    _console.print(
        f"[bold]curlcmd setup[/bold] — método de instalação detectado: [cyan]{features.install_method()}[/cyan]"
    )

    # Nothing chosen and not --yes: run the real interactive flow (or, on a
    # non-TTY, explain how to run it non-interactively — never a silent no-op).
    if not selected and not want_payloads and not assume_yes:
        if not sys.stdin.isatty():
            _print_feature_status()
            _console.print(
                "\n[yellow]Sem terminal interativo.[/yellow] Rode [bold]curlcmd setup --yes[/bold] "
                "(instala tudo) ou escolha grupos: [bold]--payloads/--browser/--proxy/--socks[/bold]."
            )
            return EXIT_OK
        selected, want_payloads = _interactive_select()
        if not selected and not want_payloads:
            _console.print("[dim]Nada selecionado. Nada a fazer.[/dim]")
            return EXIT_OK

    if features.is_frozen() and selected:
        _console.print(
            "[red]Recusado:[/red] os recursos opcionais (navegador, proxy, SOCKS, área de "
            "transferência) dependem de pacotes Python e [bold]não podem[/bold] ser instalados "
            "dentro do binário standalone.\n"
            "Instale o curlcmd via Python — por exemplo [bold]pipx install curlcommander[/bold] — "
            "e rode o setup a partir dele."
        )
        return EXIT_USAGE

    ok = True
    if selected:
        ok = _install_features(selected, assume_yes) and ok
    if want_payloads:
        ok = _sync_payloads(assume_yes) and ok

    if ok:
        _console.print("\n[green]Setup concluído.[/green] Rode [bold]curlcmd doctor[/bold] para conferir.")
        return EXIT_OK
    _console.print(
        "\n[yellow]Setup terminou com pendências.[/yellow] Veja as mensagens acima e rode "
        "[bold]curlcmd doctor[/bold] para o diagnóstico detalhado."
    )
    return EXIT_USAGE


def _install_features(selected: list[str], assume_yes: bool) -> bool:
    """Install the pip packages for the selected features + their post steps."""
    missing = [name for name in selected if not features.available(name)]
    already = [name for name in selected if features.available(name)]
    for name in already:
        _console.print(f"[green]✓[/green] {features.FEATURES[name].label} já disponível — nada a fazer.")

    if not missing:
        # Still run post-install steps that may be pending (e.g. chromium).
        return _run_post_install(selected, assume_yes)

    packages = features.packages_for(missing)
    _console.print(
        "\nVou instalar os pacotes abaixo com pip (baixando do PyPI pela rede):\n"
        + "\n".join(f"  • {pkg}" for pkg in packages)
    )
    if not _confirm("Prosseguir com a instalação?", assume_yes):
        return False

    if not _run(features.pip_install_command(packages)):
        _console.print(
            "[red]A instalação via pip falhou.[/red] Se o curlcmd foi instalado com pipx, tente "
            f"[bold]pipx inject curlcommander {' '.join(packages)}[/bold]; com uv, "
            f"[bold]uv tool install --force curlcommander --with {' --with '.join(packages)}[/bold]."
        )
        return False

    return _run_post_install(missing, assume_yes)


def _run_post_install(names: list[str], assume_yes: bool) -> bool:
    """Run post-install steps (e.g. `playwright install chromium`)."""
    ok = True
    if "browser" in names:
        # Playwright ships its own browser downloader; only run it if chromium
        # is not already present (idempotent).
        from curlcommander.core import browser

        if browser.browser_available() and browser.chromium_executable() is None:
            _console.print("\nO Playwright precisa baixar o Chromium (download pela rede, ~150 MB).")
            if _confirm("Baixar o Chromium agora?", assume_yes):
                ok = _run([sys.executable, "-m", "playwright", "install", "chromium"]) and ok
            else:
                _console.print(
                    "[yellow]Chromium não baixado.[/yellow] Rode depois: "
                    "[bold]python -m playwright install chromium[/bold]"
                )
        elif browser.browser_available():
            _console.print("[green]✓[/green] Chromium já disponível.")
    return ok


def _sync_payloads(assume_yes: bool) -> bool:
    """Clone/refresh the payload sources (SecLists/etc.)."""
    from curlcommander.core import payload_sources

    _console.print("\nVou sincronizar as fontes de payloads (git clone/atualização pela rede).")
    if not _confirm("Sincronizar as wordlists agora?", assume_yes):
        return False
    ok = True
    try:
        for name in payload_sources.load_sources():
            dest = payload_sources.sync(name)
            _console.print(f"[green]sincronizado[/green] {name} → {dest}")
    except payload_sources.PayloadSourceError as exc:
        _console.print(f"[red]Erro ao sincronizar payloads:[/red] {exc}")
        ok = False
    return ok


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    essential: bool = False
    fix_feature: str | None = None  # setup feature name to install on --fix
    fix_payloads: bool = False
    fix_hint: str = ""  # manual command shown when not auto-fixable


def _gather_checks() -> list[Check]:
    from curlcommander.config import app_dir

    checks: list[Check] = []

    # Python version (essential).
    v = sys.version_info
    py_ok = (v.major, v.minor) >= (3, 11)
    checks.append(
        Check(
            name="Python 3.11+",
            ok=py_ok,
            detail=f"{v.major}.{v.minor}.{v.micro}",
            essential=True,
            fix_hint="Instale Python 3.11 ou mais novo.",
        )
    )

    # Install method (informational).
    checks.append(Check(name="Instalação", ok=True, detail=features.install_method()))

    # Config dir writable (essential).
    d = app_dir()
    writable = True
    detail = str(d)
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".curlcmd-doctor-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        writable = False
        detail = f"{d} — sem escrita: {exc}"
    checks.append(
        Check(
            name="Diretório de dados gravável",
            ok=writable,
            detail=detail,
            essential=True,
            fix_hint="Ajuste as permissões do diretório ou defina CURLCOMMANDER_HOME.",
        )
    )

    # Optional features.
    for fname in _FEATURE_FLAGS:
        feat = features.FEATURES[fname]
        avail = features.available(fname)
        checks.append(
            Check(
                name=feat.label,
                ok=avail,
                detail="disponível" if avail else "ausente",
                essential=False,
                fix_feature=None if avail else fname,
                fix_hint="" if avail else f"curlcmd setup --{fname}",
            )
        )

    # Chromium, only meaningful when the browser extra is present.
    if features.available("browser"):
        from curlcommander.core import browser

        exe = browser.chromium_executable()
        has_chromium = exe is not None
        checks.append(
            Check(
                name="Chromium (Playwright)",
                ok=has_chromium,
                # A None here can still mean "Playwright's bundled browser"; we
                # only report what we can positively locate.
                detail=exe or "não localizado por caminho explícito",
                essential=False,
                fix_feature="browser" if not has_chromium else None,
                fix_hint="" if has_chromium else "python -m playwright install chromium",
            )
        )

    # Payload sources (informational).
    try:
        from curlcommander.core import payload_sources

        synced = [n for n in payload_sources.load_sources() if payload_sources.is_available(n)]
        checks.append(
            Check(
                name="Fontes de payloads",
                ok=bool(synced),
                detail=", ".join(synced) if synced else "nenhuma sincronizada",
                essential=False,
                fix_payloads=not synced,
                fix_hint="" if synced else "curlcmd setup --payloads",
            )
        )
        # Freshness (0.3): a synced source not refreshed in > STALE_AFTER_DAYS.
        if synced:
            stale = payload_sources.stale_sources()
            checks.append(
                Check(
                    name="Frescor das wordlists",
                    ok=not stale,
                    detail=(
                        f"desatualizadas (> {payload_sources.STALE_AFTER_DAYS} dias): {', '.join(stale)}"
                        if stale
                        else "atualizadas"
                    ),
                    essential=False,
                    fix_hint="" if not stale else "curlcmd payloads update",
                )
            )
    except Exception:  # pragma: no cover - payload module optional at runtime
        pass

    return checks


def run_doctor(args) -> int:
    """`curlcmd doctor [--fix]` — diagnose the install; --fix installs what it can."""
    fix = getattr(args, "fix", False)
    checks = _gather_checks()

    table = Table(title="curlcmd doctor", show_lines=False)
    table.add_column("")
    table.add_column("Verificação")
    table.add_column("Detalhe", overflow="fold")
    table.add_column("Correção", overflow="fold")
    for c in checks:
        mark = "[green]✓[/green]" if c.ok else ("[red]✗[/red]" if c.essential else "[yellow]○[/yellow]")
        table.add_row(mark, c.name, c.detail, "" if c.ok else c.fix_hint)
    _console.print(table)

    essential_fail = [c for c in checks if c.essential and not c.ok]
    optional_fail = [c for c in checks if not c.essential and not c.ok]

    if fix and optional_fail:
        _console.print("\n[bold]--fix:[/bold] tentando resolver o que for automático…")
        want_features = sorted({c.fix_feature for c in optional_fail if c.fix_feature})
        want_payloads = any(c.fix_payloads for c in optional_fail)
        if features.is_frozen() and want_features:
            _console.print(
                "[yellow]Recursos opcionais não podem ser instalados no binário standalone.[/yellow] "
                "Use uma instalação via Python (pipx install curlcommander)."
            )
        else:
            if want_features:
                _install_features(list(want_features), assume_yes=getattr(args, "yes", False))
            if want_payloads:
                _sync_payloads(assume_yes=getattr(args, "yes", False))
        _console.print("[dim]Reexecute 'curlcmd doctor' para confirmar.[/dim]")

    if essential_fail:
        _console.print(
            f"\n[red bold]{len(essential_fail)} verificação(ões) essencial(is) falhou(ram).[/red bold] "
            "Corrija-as antes de usar o curlcmd."
        )
        return EXIT_USAGE

    if optional_fail and not fix:
        _console.print(
            f"\n[yellow]{len(optional_fail)} recurso(s) opcional(is) ausente(s).[/yellow] "
            "Instale com [bold]curlcmd setup ...[/bold] ou [bold]curlcmd doctor --fix[/bold]."
        )
    else:
        _console.print("\n[green]Tudo essencial em ordem.[/green]")
    return EXIT_OK


# ---------------------------------------------------------------------------
# self-update
# ---------------------------------------------------------------------------

# How to update / remove curlcmd for each detected install method (PT-BR).
_UPDATE_HINTS: dict[str, tuple[str, str]] = {
    "pipx": ("pipx upgrade curlcommander", "pipx uninstall curlcommander"),
    "uv tool": ("uv tool upgrade curlcommander", "uv tool uninstall curlcommander"),
    "ambiente virtual (venv)": (
        "python -m pip install --upgrade curlcommander",
        "python -m pip uninstall curlcommander",
    ),
    "Python do sistema": (
        "python -m pip install --upgrade curlcommander",
        "python -m pip uninstall curlcommander",
    ),
}


def run_self_update(args) -> int:
    """`curlcmd self-update [--yes]` — update curlcmd using the detected method."""
    method = features.install_method()
    _console.print(f"[bold]curlcmd self-update[/bold] — método: [cyan]{method}[/cyan]")

    if features.is_frozen():
        _console.print(
            "[yellow]Você está usando o binário standalone.[/yellow] Ele não se atualiza sozinho: "
            "baixe a versão mais recente na página de releases do GitHub e substitua o arquivo. "
            "Para remover, apague o binário e o diretório de dados (veja 'curlcmd doctor')."
        )
        return EXIT_OK

    hint = _UPDATE_HINTS.get(method)
    if hint is None:
        _console.print(
            "[yellow]Não consegui determinar o comando de atualização com segurança.[/yellow] "
            "Use o mesmo gerenciador com que instalou (pipx/uv/pip)."
        )
        return EXIT_USAGE

    update_cmd, uninstall_cmd = hint
    _console.print(f"Atualizar: [bold]{update_cmd}[/bold]")
    _console.print(f"Desinstalar: [bold]{uninstall_cmd}[/bold]")
    if not _confirm("Rodar a atualização agora?", getattr(args, "yes", False)):
        _console.print("[dim]Nenhuma alteração feita.[/dim]")
        return EXIT_OK
    return EXIT_OK if _run(update_cmd.split()) else EXIT_USAGE


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------


def _print_feature_status() -> None:
    table = Table(title="Recursos opcionais", show_lines=False)
    table.add_column("")
    table.add_column("Recurso")
    table.add_column("Como habilitar")
    for name in _FEATURE_FLAGS:
        feat = features.FEATURES[name]
        avail = features.available(name)
        mark = "[green]✓[/green]" if avail else "[yellow]○[/yellow]"
        table.add_row(mark, feat.label, "" if avail else f"curlcmd setup --{name}")
    _console.print(table)
