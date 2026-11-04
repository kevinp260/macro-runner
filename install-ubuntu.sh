#!/usr/bin/env bash
set -euo pipefail

if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  echo "Warning: desktop input automation may not work under Wayland. Use an Ubuntu on Xorg session."
fi

if ! command -v pipx >/dev/null 2>&1; then
  echo "Install pipx and Tk first: sudo apt install pipx python3-tk python3-dev"
  exit 1
fi

cd "$(dirname "$0")"
pipx install --force .
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/macro-runner.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MacroRunner
Comment=Mouse and keyboard macro runner
Exec=$HOME/.local/bin/macro-runner
Icon=input-mouse
Terminal=false
Categories=Utility;
EOF
echo "Installed. Find MacroRunner in the application launcher, or run ~/.local/bin/macro-runner"
