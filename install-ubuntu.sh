#!/usr/bin/env bash
set -euo pipefail

# This is a per-user pipx installation. Only explicitly approved APT operations
# are elevated; running the whole install under sudo would install to root.
if [[ "$(id -u)" -eq 0 ]]; then
  echo "Do not run this installer with sudo. Run 'make install' as your normal user." >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1 || ! command -v dpkg-query >/dev/null 2>&1; then
  echo "This installer requires an Ubuntu/Debian-based system with APT." >&2
  exit 1
fi

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mapfile -t qt_packages < <(grep -Ev '^[[:space:]]*(#|$)' "$repo_dir/packaging/ubuntu-dependencies.txt")
packages=(pipx python3-venv "${qt_packages[@]}")
missing=()
for package in "${packages[@]}"; do
  if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -Fxq 'install ok installed'; then
    missing+=("$package")
  fi
done

if (("${#missing[@]}" > 0)); then
  printf 'MacroRunner needs the following missing Ubuntu packages:\n'
  printf '  - %s\n' "${missing[@]}"
  printf 'Only these missing packages will be installed using APT.\n'
  if [[ "${MACRORUNNER_INSTALL_ASSUME_YES:-}" != 1 ]]; then
    if [[ ! -t 0 ]]; then
      echo "No interactive terminal for confirmation; install the packages above manually, then retry." >&2
      exit 1
    fi
    read -r -p 'Install the missing system packages now? [y/N] ' answer
    case "$answer" in
      y|Y|yes|YES|Yes) ;;
      *) echo "Cancelled. No system changes made."; exit 1 ;;
    esac
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is unavailable. Ask an administrator to install the packages shown above." >&2
    exit 1
  fi
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends -- "${missing[@]}"
else
  echo 'All required Ubuntu system packages are installed.'
fi

if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
  echo 'Warning: input automation and global hotkeys can be restricted on Wayland. Prefer Ubuntu on Xorg.'
fi
if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx is not available after APT installation." >&2
  exit 1
fi

cd "$repo_dir"
pipx install --force .
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/macro-runner.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MacroRunner
Comment=Mouse and keyboard macro workflow editor
Exec=$HOME/.local/bin/macro-runner
Icon=input-mouse
Terminal=false
Categories=Utility;
EOF
echo "Installed MacroRunner. Launch from the app menu or $HOME/.local/bin/macro-runner"
echo 'If the macro-runner command is missing from PATH, run: pipx ensurepath'
