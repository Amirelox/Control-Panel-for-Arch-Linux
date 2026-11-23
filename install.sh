#!/usr/bin/env bash
# Install Control Panel for the current user.
#
#   ./install.sh            install (venv + launcher + desktop entry)
#   ./install.sh --uninstall remove the launcher and desktop entry
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_DIR/applications"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$BIN_DIR/control-panel" "$APP_DIR/control-panel.desktop"
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
    echo "Removed launcher and desktop entry. The checkout and .venv were kept."
    exit 0
fi

command -v python3 >/dev/null 2>&1 || {
    echo "python3 is required." >&2
    exit 1
}

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating virtual environment ..."
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$ROOT"

mkdir -p "$BIN_DIR" "$APP_DIR"
ln -sfn "$ROOT/run.sh" "$BIN_DIR/control-panel"

sed "s|@EXEC@|$BIN_DIR/control-panel|g" \
    "$ROOT/packaging/control-panel.desktop" > "$APP_DIR/control-panel.desktop"
chmod 644 "$APP_DIR/control-panel.desktop"

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true

echo
echo "Installed."
echo "  Launcher: $BIN_DIR/control-panel"
echo "  Desktop:  $APP_DIR/control-panel.desktop"
echo
echo "Make sure $BIN_DIR is in your PATH."
