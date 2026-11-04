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

- ✅ **Actions**: Click / Wait / Key (press or type) / Move
- ✅ **Per‑action repeat counters**
- ✅ **Whole‑sequence Repeat count** (top bar)
- ✅ **Recording (mouse clicks)** inside Click tab
  - Insert waits between clicks (with minimum threshold)
  - Per‑recorded‑action repeats
- ✅ **Pick** coordinates with a 3‑second countdown
- ✅ **Save / Load** sequences as JSON
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

## Save / Load Sequences

- **Save Sequence** writes a `.json` with the list of actions.
- **Load Sequence** restores it. You can keep multiple recipes and reuse them.

Example JSON snippet:

```json
[
  {
    "kind": "click",
    "repeats": 1,
    "x": 1200,
    "y": 640,
    "button": "left",
    "clicks": 1,
    "interval": 0.0
  },
  { "kind": "wait", "repeats": 1, "seconds": 2.0 },
  {
    "kind": "click",
    "repeats": 1,
    "x": 980,
    "y": 420,
    "button": "left",
    "clicks": 1,
    "interval": 0.0
  },
  { "kind": "key", "repeats": 1, "key_mode": "press", "keys": "enter" }
]
```

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
