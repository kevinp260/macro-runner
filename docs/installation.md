# MacroRunner installation and distribution

MacroRunner uses the same Python/PySide6 application on Ubuntu and Windows.
Binary installers are built separately on each operating system.

## Ubuntu: source installation

Run `make install` as your normal user from the repository. The script
checks APT dependencies, displays any missing packages, requests confirmation
before sudo, installs only missing packages through APT, then installs
MacroRunner in your user account using pipx. It creates the app-menu shortcut.

```bash
git pull origin main
make install
~/.local/bin/macro-runner
```

The script does not use sudo for the pipx application itself. It fails safely
without interactive confirmation, unless MACRORUNNER_INSTALL_ASSUME_YES=1 is
explicitly supplied by the operator. `make uninstall` removes the pipx
application and app-menu launcher, but leaves shared APT libraries installed.

## Ubuntu: standalone .deb

Download `macrorunner_<version>_amd64.deb` from the GitHub Actions
**Build desktop installers** workflow and run:

```bash
sudo apt install ./macrorunner_<version>_amd64.deb
```

APT automatically resolves the declared native Qt/X11 and screenshot
dependencies. The package includes the application executable, bundled Python
runtime and Python packages, application-menu entry and icon.

The .deb is built and tested for **Ubuntu 24.04 amd64**. Xorg/X11 is recommended
for reliable desktop input automation. Other Linux distributions and Wayland
are not guaranteed. Remove with `sudo apt remove macrorunner`.

**Choose one Ubuntu installation method.** pipx and the .deb both expose
`macro-runner` commands; uninstall one before switching.

## Windows

Download `MacroRunner-Setup-<version>.exe` from the same GitHub Actions
workflow. Run it to install the Windows application, Start Menu shortcut and
Desktop shortcut. Python and Qt are bundled in the executable; users do not
need to install Python or Qt separately.

The existing Inno Setup AppId is preserved for upgrades. Windows SmartScreen
may warn about unsigned installers. Code-sign builds before broad public
distribution.

## Building locally

Ubuntu: `make setup && make build && make deb`. The .deb builder requires
dpkg-deb and Pillow in the Python environment used for icon conversion.

Windows: install Python, PyInstaller and Inno Setup 6, then run:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e . pyinstaller
.venv\Scripts\python -m PyInstaller --clean --noconfirm MacroRunner.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer.iss
```

GitHub Actions builds both formats and uploads separate downloadable artifacts.
Ubuntu CI installs the .deb and launches the app under a virtual X display;
Windows CI compiles the setup executable. Manual desktop QA remains necessary
for recording, screenshots, global hotkeys, and workflow drag-and-drop.
