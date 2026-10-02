#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugins_dir="$HOME/.local/share/caelestia/plugins"
mkdir -p "$plugins_dir"
ln -sfn "$root" "$plugins_dir/captive-portal"

echo "Installed Caelestia CaptivePortal plugin at $plugins_dir/captive-portal"
echo "Reload Caelestia plugins or restart the shell to activate it."
