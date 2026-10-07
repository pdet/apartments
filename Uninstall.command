#!/bin/bash
# Double-click to stop the apartment watcher and remove it from this Mac.
set -euo pipefail
trap 'echo "Removal failed. Read the error above, then run Uninstall.command again."; read -r -p "Press Enter to close this window." || true' ERR
LAUNCH_TARGET="gui/$(id -u)/nl.apartment-watcher"
if launchctl print "$LAUNCH_TARGET" >/dev/null 2>&1; then
  launchctl bootout "$LAUNCH_TARGET"
fi
rm -f "$HOME/Library/LaunchAgents/nl.apartment-watcher.plist"
rm -rf "$HOME/Library/Application Support/apartment-watcher"
echo "The apartment watcher has been removed."
read -r -p "Press Enter to close this window."
