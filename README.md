# MacroRunner (Mouse/Keyboard Automator)

A tiny desktop app that records and plays back mouse/keyboard actions. Great for repetitive tasks like:

- click at **X,Y** → wait **N** seconds → press a key → **repeat 80×**
- quick data entry sequences
- UI smoke tests

> **Emergency stop:** move the mouse to the **top‑left corner** of the screen (PyAutoGUI failsafe).

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Project Setup (Dev)](#project-setup-dev)
- [Run the App (Dev)](#run-the-app-dev)
- [Build a Standalone EXE (PyInstaller)](#build-a-standalone-exe-pyinstaller)
- [Window Icon (Tk) + Resources](#window-icon-tk--resources)
- [Create a Windows Installer (Inno Setup)](#create-a-windows-installer-inno-setup)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Recording Mode](#recording-mode)
- [Typical Workflow Example](#typical-workflow-example)
- [Save / Load Sequences](#save--load-sequences)
- [Troubleshooting & Tips](#troubleshooting--tips)
- [License](#license)

---

## Overview

**MacroRunner** is a lightweight GUI tool (Tkinter + PyAutoGUI) that lets you construct a list of actions:

- **Click** at a given screen coordinate (choose button, multi‑click, intra‑click interval)
- **Wait** for N seconds
- **Key / Type** a key or a text snippet (supports key combos like `ctrl+s`)
- **Move** the mouse to a location (no click)

You can **repeat each action** multiple times (per‑action repeats) and **repeat the entire sequence** (whole‑sequence repeats).  
A **Recording (mouse clicks)** box lives inside the **Click** tab to capture real clicks from anywhere on screen, optionally inserting **Wait** actions based on time gaps.

---

## Features

- ✅ **Actions**: Click / Wait / Key (press or type) / Move / Scroll / Drag
- ✅ **Pause / Resume** (button or F6), execution progress and active-action selection
- ✅ **Scroll** and **Drag** actions
- ✅ **Repeat Blocks** (Loop Start / Loop End) with independent cycle count
- ✅ **Per‑action repeat counters**
- ✅ **Whole‑sequence Repeat count** (top bar)
- ✅ **Recording (mouse clicks)** inside Click tab
  - Insert waits between clicks (with minimum threshold)
  - Per‑recorded‑action repeats
- ✅ **Pick** coordinates with a 3‑second countdown
- ✅ **Save / Load** sequences as JSON (including repeat count and start delay)
- ✅ **Edit any action** by double-clicking; optionally change its action type
- ✅ **Enable / disable** actions without deleting them
- ✅ **Emergency stop**: move to top‑left corner
- ✅ **Keyboard shortcuts** for fast editing
- ✅ **Single‑instance mutex** (optional) so only one app instance runs
- ✅ **Pack as a single .exe** and an **Inno Setup** installer

---

## Requirements

- **OS**: Windows 10/11 (primary target).

  > macOS/Linux may work with the same code, but OS‑level permissions/accessibility differ. macOS needs Accessibility permissions for controlling input. Linux may need additional deps (e.g., `scrot`).

- **Python**: 3.8+ (dev usage).

- **Python packages**:

  ```bash
  pip install pyautogui pillow pynput
  ```

  - **pyinstaller** (build only): `pip install pyinstaller`

- Optional but recommended for installer builds:
  - **Inno Setup** (Windows) — to produce a proper installer.

---

## Ubuntu installation (X11 / Xorg)

MacroRunner now supports Python installation on Ubuntu. **Use an X11/Xorg desktop
session**, not Wayland, for reliable PyAutoGUI/Pynput input automation.
On the Ubuntu login screen choose the gear icon and select *Ubuntu on Xorg*
when available. Do not run MacroRunner as root.

Install prerequisites:

```bash
sudo apt update
sudo apt install python3-tk python3-dev pipx
pipx ensurepath
```

From the cloned project folder run `bash install-ubuntu.sh`. The script installs
the app with `pipx` and adds a user-level launcher (MacroRunner) to your app menu.
Alternatively run `pipx install .` and `~/.local/bin/macro-runner` directly.

On Windows, the existing PyInstaller/Inno Setup installer remains unchanged.

---

## Build, install and manual QA

Use [the manual QA checklist](docs/manual-tests.md) to verify all changes after PRs 1–3.

### Ubuntu (Xorg/X11)

First install one-time prerequisites:

```bash
sudo apt update
sudo apt install make python3-venv python3-tk python3-dev pipx
pipx ensurepath
```

From the repository folder:

```bash
make install       # pipx installation + application launcher; no build required
make setup         # optional development environment
make test          # unit tests (requires make setup)
make run           # run development version
make build         # optional standalone executable: dist/MacroRunner
make uninstall     # uninstall after QA is finished
```

Use `make help` to see the commands. Override variables if needed, e.g. `make setup PYTHON=python3.12 VENV=.venv312`.

Use **an Xorg/X11 session** for actual input control; `echo $XDG_SESSION_TYPE` can confirm it. Wayland sessions may prevent automation.

### Windows (PowerShell)

GNU Make is not installed by default on Windows, so the native one-time commands are simpler:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pyinstaller
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean MacroRunner.spec
```

Launch `dist\MacroRunner.exe` to test the standalone build. To create the installable Windows setup, first install **Inno Setup 6**, then run:

```powershell
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" .\installer.iss
Start-Process .\Output\MacroRunner-Setup-1.5.5.exe
```

Check `installer.iss` for the installer version if it has changed. Install/test on the same OS type used for the build; PyInstaller does not cross-compile.

---
## Project Setup (Dev)

```bash
python -m venv .venv
# Windows:
. .venv/Scripts/activate
pip install pyautogui pillow pynput
```

Put your script as **`macro_runner.py`** (the app in this repo).

---

## Run the App (Dev)

```bash
python macro_runner.py
```

---

## Build a Standalone EXE (PyInstaller)

Include your app icon so Explorer/Taskbar shows it immediately:

```bash
pyinstaller --onefile --windowed --name "MacroRunner" \
  --icon macro_runner_icon.ico \
  --add-data "macro_runner_icon.ico;." \
  macro_runner.py
```

- `--icon` embeds the icon into the EXE.
- `--add-data` also ships the `.ico` so Tk can load it at runtime (see next section).  
  On macOS/Linux, use `--add-data "macro_runner_icon.ico:."` (colon instead of semicolon).

Output will be under `dist/MacroRunner.exe`.

---

## Window Icon (Tk) + Resources

Tk’s title‑bar icon is set at runtime. Add this helper and call `iconbitmap` after creating the app:

```python
import os, sys

def resource_path(rel):
    try:
        base = sys._MEIPASS  # set by PyInstaller
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, rel)

if __name__ == "__main__":
    app = MacroRunnerApp()
    try:
        app.iconbitmap(resource_path("macro_runner_icon.ico"))
    except Exception:
        pass
    app.mainloop()
```

> **Note:** Shipping the `.ico` as data (see `--add-data`) ensures the icon exists on disk when the EXE runs.

---

## Create a Windows Installer (Inno Setup)

A minimal, upgrade‑friendly script. **Keep the `AppId` GUID constant** across releases.  
Save as `installer.iss` and build in Inno Setup.

```ini
#define MyAppName     "MacroRunner"
#define MyAppVersion  "1.2.1"                ; bump every release
#define MyAppId       "{8F6B8A3D-5D6E-4E62-9C0D-0D0FBF9A8F22}"  ; keep stable

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; Icons
SetupIconFile=icon\macro_runner_icon.ico
UninstallDisplayIcon={app}\MacroRunner.exe

; Upgrade friendliness
UsePreviousAppDir=yes
DisableDirPage=yes
DisableProgramGroupPage=yes

; Close running instances to update
CloseApplications=yes
RestartApplications=no

; Optional: coordinate with a mutex you create in Python
AppMutex=Global\MacroRunnerMutex

[Files]
Source: "dist\MacroRunner.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MacroRunner"; Filename: "{app}\MacroRunner.exe"
Name: "{commondesktop}\MacroRunner"; Filename: "{app}\MacroRunner.exe"
```

If you added the suggested mutex in Python, keep this near the top of `macro_runner.py`:

```python
import ctypes, sys
def _single_instance_mutex():
    m = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\MacroRunnerMutex")
    if ctypes.GetLastError() == 183:
        from tkinter import messagebox
        messagebox.showerror("Already running", "MacroRunner is already running.")
        sys.exit(0)
_single_instance_mutex()
```

---

## Keyboard Shortcuts

- **Run** — `F5`
- **Stop** — `Esc`
- **Pause / Resume** — `F6`
- **Delete selected** — `Del`
- **Duplicate selected** — `Ctrl+Shift+D` (`⌘⇧D` on macOS)
- **Move selected** — `Ctrl+↑ / Ctrl+↓`
- **Edit repeat** — `Ctrl+E`
- **Save** — `Ctrl+S`
- **Load** — `Ctrl+O`
- **Start/Stop recording** — `Ctrl+R`

> Shortcuts are disabled while your caret is inside a text field to avoid accidental triggers.

---

## Recording Mode

Inside the **Click** tab, open **Recording (mouse clicks)**:

1. **Start Recording** — 3‑second countdown, then clicks anywhere are captured.
2. Optional: **Insert waits between clicks** — creates **Wait** actions when time gaps ≥ **Min wait (s)**.
3. **Recorded repeats (x)** — per‑click repeats applied to captured clicks.
4. **Stop Recording** to finish.

Captured actions are appended to the list; you can reorder, duplicate, or delete them.

---

## Typical Workflow Example

**Task:** “Click A → wait 2s → click B → press Enter → repeat 80×”

1. Click tab → **Pick** spot A → **Add Click Action**
2. Wait tab → Seconds `2.0` → **Add Wait Action**
3. Click tab → **Pick** spot B → **Add Click Action**
4. Key tab → Mode `press`, key `enter` → **Add Key Action**
5. Top bar → **Repeat count (whole sequence) = 80**
6. Put the target app in the foreground → **Run**
7. To abort at any time, move mouse to **top‑left corner**.

---

## Playback controls

Run a sequence with **F5**, pause/resume with **F6**, and stop with **Esc**.
The progress label shows the current loop and executed action step, and the
active action is selected in the list. Pause works between actions and during
Wait/start-delay; an in-progress operating-system mouse drag or move cannot be
interrupted midway. Stop remains available while paused.

The **Scroll** tab adds mouse wheel steps (positive = up, negative = down).
The **Drag** tab moves from a starting coordinate to an end coordinate while
holding a selected mouse button. Both types can be edited by double-clicking
them and are saved in the existing version-2 JSON format.

Keyboard-event recording has intentionally been deferred: it requires a
separate permission and input-safety review, and was not necessary for PR 3.

## Repeat Blocks (subloops)

Use **Loop** tab to repeat a group of consecutive actions. For example:

```text
Action A
Action B
Loop Start (5 cycles)
    Action C
    Action D
Loop End
Action E
```

This executes A, B, then C/D five times, then E. If the whole-sequence
repeat count is 3, the entire operation runs three times. Individual
action repeat counts also work inside blocks.

To place markers around **existing** actions, select C and choose
**Insert Loop Start** (inserts before C); then select D and choose
**Insert Loop End** (inserts after D). With no action selected,
markers append to the end of the list. Rename Loop Start and edit its
cycle count by double-clicking it.

Only **one level of subloop** is supported. Loop markers must be
paired, with at least one action between them; nested, incomplete and
empty loops are rejected when running, saving or loading. Loop markers
cannot be disabled or duplicated separately. Normal actions inside
the block can still be enabled/disabled, renamed, reordered and duplicated.
Pause and Stop work between actions in every loop cycle.

The existing version-2 JSON file format is retained, and older macros
remain compatible.

## Edit and manage actions

Double-click an action (or select it and press **Edit…**) to change its name,
repeat count, type, and applicable settings. Changes are applied only after
validation when you press **Save**. Select an action and click **Enable/Disable**
to skip it during playback without deleting it. Disabled actions appear with
an `[OFF]` prefix. Duplicate, Rename, Edit Repeat, Up/Down and Delete still work.

## Save / Load Sequences

**Save** writes a versioned JSON document that includes the action list,
whole-sequence repeat count, and start delay:

```json
{
  "version": 2,
  "settings": {"repeat_count": 80, "start_delay": 3.0},
  "actions": [
    {"kind": "click", "x": 1200, "y": 640, "repeats": 2, "enabled": true},
    {"kind": "wait", "seconds": 1.0, "enabled": false}
  ]
}
```

**Load** supports this new format and older JSON files containing just an array
of actions. When loading an old file, the currently entered whole-sequence
repeat and start delay are left unchanged. Existing actions default to enabled.

---

## Troubleshooting & Tips

- **Icon shows Python/Tk feather**  
  Rebuild with `--icon macro_runner_icon.ico` and also ship the file with `--add-data`. Call `app.iconbitmap(...)`. Windows Explorer may cache icons—bump version or clear icon cache if needed.

- **Installer says “app is running”**

  - Keep `CloseApplications=yes` in Inno Setup.
  - Add a **Global mutex** in the app (`AppMutex` + `_single_instance_mutex()` above).
  - Ensure you’re not launching the app at the end of install.

- **DPI / multi‑monitor**  
  For pixel‑perfect targets, keep the automated app on the **primary monitor** and avoid moving windows during playback.

- **macOS/Linux**  
  Grant Accessibility (macOS) / install extra tools (Linux) if needed for PyAutoGUI to control input.

---

## License

MIT (or your preferred license).
