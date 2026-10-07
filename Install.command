#!/bin/bash
# Double-click to install the apartment watcher, or to change its settings.
set -euo pipefail
trap 'echo "Installation failed. Read the error above, then run Install.command again."; read -r -p "Press Enter to close this window." || true' ERR
cd "$(dirname "$0")"
APP="$HOME/Library/Application Support/apartment-watcher"
LAUNCH_TARGET="gui/$(id -u)/nl.apartment-watcher"
RESTORE_SERVICE=0

restore_service() {
  if [ "$RESTORE_SERVICE" -eq 1 ] && ! launchctl print "$LAUNCH_TARGET" >/dev/null 2>&1; then
    echo "Restarting the existing apartment watcher..."
    launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/nl.apartment-watcher.plist" || echo "Could not restart the watcher. Run Install.command again."
  fi
}
trap restore_service EXIT

if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "Installing uv, the tool that runs the watcher..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

# Run from Application Support: macOS blocks background apps from Documents, Desktop and Downloads.
mkdir -p "$APP"
if launchctl print "$LAUNCH_TARGET" >/dev/null 2>&1; then
  launchctl bootout "$LAUNCH_TARGET"
  RESTORE_SERVICE=1
fi
if [ "$(pwd -P)" != "$(cd "$APP" && pwd -P)" ]; then
  rsync -a --delete --exclude .git --exclude .venv --exclude .env --exclude data --exclude '*.log' ./ "$APP/"
fi
cd "$APP"
"$UV" sync --locked --no-dev --quiet
.venv/bin/python -m apartment_watcher.setup_wizard
RESTORE_SERVICE=0
read -r -p "Press Enter to close this window."
