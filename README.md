# MacroRunner

MacroRunner is a Python desktop automation app for building and running mouse,
keyboard, and screenshot-based workflows. Version 2 uses **PySide6 / Qt Widgets**
and a **structured workflow editor**, replacing the former Tkinter interface.

## Interface

- **Action palette (left):** Search actions, double-click to add, or drag into
  the workflow. Click Image opens a reference-image picker.
- **Workflow editor (center):** Sequential action cards and collapsible Repeat,
  If/Else and Repeat Until groups. Drag to reorder actions or complete groups,
  including moving between compatible groups. Invalid moves revert immediately.
  Ctrl/Shift-click selects multiple items; Delete and Duplicate apply to
  selected nodes. Undo/Redo restores up to 60 snapshots.
- **Properties (right):** Scrollable inspector with relevant fields for the
  selected action. Click **Apply changes** after editing.
- **Toolbar:** New, Open, Save, Run, Pause/Resume, Stop, Step,
  Run from Selected, Record, Undo and Redo.
- **Footer:** Whole-workflow repeat count, start delay, optional **Minimize when running**
  checkbox, and progress. When enabled, MacroRunner minimizes before the start
  delay and restores after completion, Stop, or execution failure. This preference
  is saved per device, independently of macro JSON.

Panel widths and window position/size persist between sessions. Use
**View → Dark theme** to switch appearance. The layout resizes and the
properties panel scrolls instead of clipping long action forms.

## Actions and workflows

Supported actions include mouse click, move, scroll, drag, wait, keyboard
press/text, Hold and Release, Click Image, Wait Until, Repeat, If/Else and
Repeat Until.

An example workflow:

```text
Click image: start.png
Wait until: pixel becomes green
Repeat 5 times
    If: target.png is visible
        Click image: target.png
    Else
        Wait 0.5 seconds
Press Enter
```

Repeat and If containers correspond to the same legacy Start/End markers in
the saved JSON. The editor **does not introduce a new macro format**.
Existing JSON version 2 macros remain supported, as do legacy action arrays.

Repeat Until requires a finite maximum number of cycles. Visual Wait and
Click Image have configurable timeouts. Image matching uses OpenCV with
confidence and optional search-region settings; pixel checks support RGB
hex colors and tolerance. These are screenshot-based features, not AI models.

**Run from Selected** and **Step** can start from a selected action. The
existing backend imposes restrictions on starting within conditional
blocks; it reports these restrictions rather than executing an invalid
partial flow.

## Recording and safety

Choose Record and configure mouse-click capture and optional keyboard
capture. Keyboard recording is **disabled by default** and requires a
privacy confirmation, because recording can capture passwords and other
sensitive input typed in other applications. There is a 3-second countdown
before recording starts. Stop ends the listeners.

The runtime releases keys held by the macro when playback finishes or
aborts. Move the mouse to the top-left corner to trigger PyAutoGUI's
emergency fail-safe while executing. Native drags may take effect until
the current drag call completes. Review recorded actions before saving
or sharing a workflow.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| F5 | Run |
| F6 | Pause/Resume (when window focused) |
| Esc | Stop (when window focused) |
| Ctrl+Alt+Shift+F6 | Global Pause/Resume (if supported) |
| Ctrl+Alt+Shift+F8 | Global Stop (if supported) |
| Ctrl+S / Ctrl+O | Save / Open |
| Ctrl+N | New |
| Ctrl+R | Start/Stop recording |
| Ctrl+Z | Undo |
| Ctrl+Y | Redo |
| Ctrl+D / Delete | Duplicate / Delete selected |

System-wide hotkeys may be unavailable in restrictive environments.

## Installation on Ubuntu and Windows

**Ready-to-install packages are built for both operating systems.**

- **Ubuntu 24.04 amd64:** Download the `.deb` installer from GitHub Actions
  **Build desktop installers** and install it with `sudo apt install ./filename.deb`.
  APT resolves the Qt and screenshot system dependencies automatically.
- **Windows x64:** Download the `MacroRunner-Setup-*.exe` installer from the
  same workflow. It bundles Python/Qt and installs Start Menu/Desktop shortcuts.
- **Ubuntu development:** Run `git pull origin main && make install` in this
  repository. The script checks for missing APT packages and asks permission
  before installing them, then installs the application using pipx.

See [installation and distribution instructions](docs/installation.md) for
full setup, upgrading, uninstalling, building, and platform limitations.

## Architecture

- `macro_runner.py` — stable executable entrypoint.
- `macro_qt.py` — Qt main window, actions, runtime feedback, recording.
- `macro_qt_workflow.py` — draggable, validated workflow tree and palette.
- `macro_qt_properties.py` — scrollable action inspector.
- `macro_workflow.py` — pure tree-to-flat representation and validation.
- `macro_runtime.py` — GUI-independent playback integration.
- `macro_model.py`, `macro_flow.py`, `macro_playback.py`,
  `macro_vision.py`, `macro_keys.py`, `macro_editing.py` — existing
  automation, validation, vision, keyboard and history services.

CI compiles and packages all runtime modules and runs model and offscreen Qt
tests on Ubuntu and Windows. Manual QA is documented in
[docs/manual-tests.md](docs/manual-tests.md).
