#!/usr/bin/env bash
set -euo pipefail

# Creates a native Ubuntu amd64 package around the PyInstaller executable.
# Requires: python3 with Pillow, dpkg-deb, and an existing dist/MacroRunner.
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo 'dpkg-deb is required to build the Ubuntu installer.' >&2
  exit 1
fi
architecture=$(dpkg --print-architecture)
if [[ "$architecture" != amd64 ]]; then
  echo "The currently supported Ubuntu binary architecture is amd64 (got $architecture)." >&2
  exit 1
fi
if [[ ! -f dist/MacroRunner ]]; then
  echo "Missing dist/MacroRunner: run 'make build' first." >&2
  exit 1
fi
version=$(python3 -m macro_version)
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid project version: $version" >&2
  exit 1
fi

mapfile -t dependencies < <(grep -Ev '^[[:space:]]*(#|$)' packaging/ubuntu-dependencies.txt)
depends=$(printf '%s, ' "${dependencies[@]}")
depends=${depends%, }

root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/DEBIAN" "$root/opt/macrorunner" "$root/usr/bin" \
         "$root/usr/share/applications" "$root/usr/share/icons/hicolor/64x64/apps"
install -m 755 dist/MacroRunner "$root/opt/macrorunner/MacroRunner"
ln -s /opt/macrorunner/MacroRunner "$root/usr/bin/macro-runner"
python3 - "$root/usr/share/icons/hicolor/64x64/apps/macrorunner.png" <<'PY'
from PIL import Image
import sys
image = Image.open("macro_runner_icon.ico")
image.seek(0)
image.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS).save(sys.argv[1])
PY
cat > "$root/usr/share/applications/macrorunner.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Version=1.0
Name=MacroRunner
Comment=Mouse and keyboard macro workflow editor
Exec=/usr/bin/macro-runner
Icon=macrorunner
Terminal=false
Categories=Utility;
StartupNotify=true
DESKTOP

cat > "$root/DEBIAN/control" <<EOF
Package: macrorunner
Version: $version
Section: utils
Priority: optional
Architecture: $architecture
Maintainer: MacroRunner Project <noreply@github.com>
Depends: $depends
Description: Structured mouse and keyboard macro workflow editor
 Desktop automation with visual image matching, keyboard capture,
 conditional workflows, and repeat blocks.
EOF
output="dist/macrorunner_${version}_${architecture}.deb"
dpkg-deb --build --root-owner-group "$root" "$output"
echo "Created $output"
