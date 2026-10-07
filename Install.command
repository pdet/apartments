#!/bin/bash
# Double-click to install the apartment watcher, or to change its settings.
set -e
cd "$(dirname "$0")"
APP="$HOME/Library/Application Support/apartment-watcher"

if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "Installing uv, the tool that runs the watcher..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

# Run from Application Support: macOS blocks background apps from Documents, Desktop and Downloads.
mkdir -p "$APP"
rsync -a --delete --exclude .git --exclude .venv --exclude .env --exclude data --exclude '*.log' ./ "$APP/"
cd "$APP"
"$UV" sync --quiet
UV="$UV" "$UV" run python -m apartment_watcher.setup_wizard
read -r -p "Press Enter to close this window."
