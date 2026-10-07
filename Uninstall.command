#!/bin/bash
# Double-click to stop the apartment watcher and remove it from this Mac.
launchctl bootout "gui/$(id -u)/nl.apartment-watcher" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/nl.apartment-watcher.plist"
rm -rf "$HOME/Library/Application Support/apartment-watcher"
echo "The apartment watcher has been removed."
read -r -p "Press Enter to close this window."
