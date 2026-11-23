#!/usr/bin/env bash
# Launch Control Panel from a local checkout.
set -euo pipefail

# Resolve symlinks (e.g. ~/.local/bin/control-panel -> this script) so the
# virtualenv and sources are always taken from the checkout, not from ~/.local/bin.
SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
    SOURCE_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ "$SOURCE" != /* ]] && SOURCE="$SOURCE_DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")" && pwd)"
VENV="$ROOT/.venv"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "First run: creating a virtual environment in $VENV ..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -e "$ROOT"
    echo "Ready."
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV/bin/python" -m control_panel "$@"
