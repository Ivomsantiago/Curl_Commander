#!/usr/bin/env bash
# CurlCommander installer.
#
# Prefers isolated installs (uv tool / pipx), falls back to a local venv, and
# only touches the system Python with --break-system-packages when you pass
# --system explicitly. Never breaks the system interpreter silently.
set -euo pipefail

cd "$(dirname "$0")"

want_system=0
for arg in "$@"; do
  case "$arg" in
    --system) want_system=1 ;;
    -h|--help)
      echo "Usage: bash install.sh [--system]"
      echo "  (default) install with uv tool / pipx, or a local .venv"
      echo "  --system  install into the system Python (--break-system-packages)"
      exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if command -v uv >/dev/null 2>&1; then
  echo "[*] Installing with uv tool…"
  uv tool install --from . curlcommander
  echo "[✓] Installed. Run: curlcmd --version"
  exit 0
fi

if command -v pipx >/dev/null 2>&1; then
  echo "[*] Installing with pipx…"
  pipx install .
  echo "[✓] Installed. Run: curlcmd --version"
  exit 0
fi

if [ "$want_system" -eq 1 ]; then
  echo "[!] --system requested: installing into the system Python."
  read -r -p "    This can break your OS Python. Continue? [y/N] " reply
  case "$reply" in
    y|Y|yes|YES) pip install --break-system-packages -e ".[dev]" ;;
    *) echo "Aborted."; exit 1 ;;
  esac
  echo "[✓] Installed. Run: curlcmd --version"
  exit 0
fi

echo "[*] uv and pipx not found — creating a local virtual environment (.venv)…"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -e ".[dev]"
echo "[✓] Installed in .venv."
echo "    Activate it with:  source .venv/bin/activate"
echo "    Then run:          curlcmd --version"
