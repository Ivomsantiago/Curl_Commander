#!/usr/bin/env sh
# Instalador remoto do CurlCommander (Linux/macOS).
#
# Uso (uma linha):
#   curl -fsSL https://raw.githubusercontent.com/Ivomsantiago/Curl_Commander/main/scripts/install.sh | sh
#
# Escolhe automaticamente o melhor método disponível, nesta ordem:
#   1. uv tool     (isolado, recomendado)
#   2. pipx        (isolado)
#   3. venv gerenciado em ~/.curlcommander/venv + atalho em ~/.local/bin
#
# É idempotente (pode rodar de novo sem quebrar) e não assume nada em silêncio:
# avisa antes de baixar da rede e ao alterar o PATH.
#
# Opções:
#   -y, --yes     Não perguntar nada (uso em scripts/CI).
#   -h, --help    Mostrar esta ajuda.
#
# Variáveis de ambiente:
#   CURLCMD_SOURCE   Instala desta origem em vez do PyPI (um caminho local ou
#                    uma especificação pip). Usado pela CI para instalar a
#                    partir do checkout: CURLCMD_SOURCE=. sh scripts/install.sh
#
# Compatível com sh/dash/bash/zsh (POSIX).
set -eu

PACKAGE="curlcommander"
SOURCE="${CURLCMD_SOURCE:-$PACKAGE}"
ASSUME_YES=0
VENV_DIR="$HOME/.curlcommander/venv"
SHIM_DIR="$HOME/.local/bin"

for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      sed -n '2,30p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'
      echo
      echo "Sem Python? Baixe um binário standalone na página de releases:"
      echo "  https://github.com/Ivomsantiago/Curl_Commander/releases"
      exit 0 ;;
    *) echo "Opção desconhecida: $arg (use --help)" >&2; exit 1 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
info() { printf '[*] %s\n' "$*"; }
ok()   { printf '[OK] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }
err()  { printf '[X] %s\n' "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

confirm() {
  # confirm "pergunta" -> 0 (sim) / 1 (não). Com --yes assume sim; sem TTY nega.
  [ "$ASSUME_YES" -eq 1 ] && return 0
  if [ ! -t 0 ]; then
    warn "Sem terminal interativo. Rode novamente com --yes para prosseguir."
    return 1
  fi
  printf '%s [s/N] ' "$1"
  read -r reply || return 1
  case "$reply" in s|S|sim|SIM|y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

on_path() {
  case ":$PATH:" in *":$1:"*) return 0 ;; *) return 1 ;; esac
}

verify() {
  # Confere se o curlcmd instalado responde. $1 = caminho ou nome do executável.
  if "$1" --version >/dev/null 2>&1; then
    ok "Instalado: $("$1" --version)"
    return 0
  fi
  warn "Instalado, mas '$1 --version' não respondeu. Verifique o PATH."
  return 1
}

offer_setup() {
  # $1 = executável do curlcmd a chamar.
  say
  if confirm "Rodar 'curlcmd setup' agora para conferir a base?"; then
    if [ "$ASSUME_YES" -eq 1 ]; then
      "$1" setup --yes || true
    else
      "$1" setup || true
    fi
  else
    say "Depois, rode:  curlcmd setup        (conferir base)"
    say "              curlcmd setup --all   (recursos opcionais + payloads)"
    say "              curlcmd doctor        (diagnóstico)"
  fi
}

install_with_uv() {
  info "Instalando com uv tool (isolado)…"
  confirm "Baixar/instalar o curlcmd via uv (usa a rede)?" || { err "Cancelado."; exit 1; }
  if [ "$SOURCE" = "$PACKAGE" ]; then
    uv tool install --force "$PACKAGE"
  else
    uv tool install --force --from "$SOURCE" "$PACKAGE"
  fi
  uv tool update-shell >/dev/null 2>&1 || true
  ok "Instalado via uv tool."
  if have curlcmd; then verify curlcmd; offer_setup curlcmd; else
    warn "curlcmd não está no PATH ainda. Abra um novo terminal ou rode: uv tool update-shell"
  fi
}

install_with_pipx() {
  info "Instalando com pipx (isolado)…"
  confirm "Baixar/instalar o curlcmd via pipx (usa a rede)?" || { err "Cancelado."; exit 1; }
  # --force torna a operação idempotente (reinstala se já existir).
  pipx install --force "$SOURCE"
  pipx ensurepath >/dev/null 2>&1 || true
  ok "Instalado via pipx."
  if have curlcmd; then verify curlcmd; offer_setup curlcmd; else
    warn "curlcmd não está no PATH ainda. Abra um novo terminal ou rode: pipx ensurepath"
  fi
}

install_with_venv() {
  info "uv e pipx não encontrados — criando um venv gerenciado em $VENV_DIR…"
  confirm "Criar o venv e baixar o curlcmd (usa a rede)?" || { err "Cancelado."; exit 1; }
  PY=""
  for cand in python3 python; do have "$cand" && { PY="$cand"; break; }; done
  [ -n "$PY" ] || { err "Python 3.11+ não encontrado. Instale o Python ou use o binário standalone."; exit 1; }

  "$PY" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV_DIR/bin/python" -m pip install --upgrade "$SOURCE"

  mkdir -p "$SHIM_DIR"
  ln -sf "$VENV_DIR/bin/curlcmd" "$SHIM_DIR/curlcmd"
  ok "Instalado no venv, com atalho em $SHIM_DIR/curlcmd."

  verify "$VENV_DIR/bin/curlcmd" || true
  if ! on_path "$SHIM_DIR"; then
    warn "$SHIM_DIR não está no seu PATH."
    say  "  Adicione ao seu shell (ex.: ~/.bashrc ou ~/.zshrc):"
    say  "    export PATH=\"$SHIM_DIR:\$PATH\""
    say  "  Depois abra um novo terminal (ou rode: source ~/.bashrc)."
  fi
  offer_setup "$VENV_DIR/bin/curlcmd"
}

main() {
  info "CurlCommander — instalador (origem: $SOURCE)"
  if have uv; then
    install_with_uv
  elif have pipx; then
    install_with_pipx
  else
    install_with_venv
  fi
}

main
