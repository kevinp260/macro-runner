# MacroRunner

MacroRunner is a Python desktop automation app for building and running mouse,
keyboard, and screenshot-based workflows. Version 2 uses **PySide6 / Qt Widgets**
and a **structured workflow editor**, replacing the former Tkinter interface.

## Interface

See **Help → About MacroRunner** for the installed application version and
repository link. `pyproject.toml` defines the version shared by Ubuntu and
Windows installers. Versioned releases are documented in [CHANGELOG.md](CHANGELOG.md).


- **Action palette (left):** Search actions, double-click to add, or drag into
  the workflow. Click Image opens a reference-image picker.
- **Workflow editor (center):** Sequential action cards and collapsible Repeat,
  If/Else and Repeat Until groups. Drag to reorder actions or complete groups,
  including moving between compatible groups. Invalid moves revert immediately.
  Each executable action has a checkbox: checked actions run, unchecked
  actions are skipped and appear muted with a strike-through and [disabled]
  label. Check/uncheck directly in the workflow, or use the inspector's
  Enabled setting or bulk Enable / Disable action. The counter also reports
  how many actions are disabled. Groups remain structural and cannot be
  disabled directly. Ctrl/Shift-click selects multiple items; Delete and
  Duplicate apply to selected nodes. Undo/Redo restores up to 60 snapshots.
- **Properties (right):** Scrollable inspector with relevant fields for the
  selected action. Click **Apply changes** after editing. Watch Region Changes
  includes **Draw screen region…**: drag a rectangle on the desktop to fill
  X/Y/width/height automatically; press Escape to cancel.
- **Toolbar:** New, Open, Save, Run, Pause/Resume, Stop, Step,
  Run from Selected, Record, Undo and Redo.
- **Footer:** Whole-workflow repeat count, start delay, optional **Minimize when running**
  checkbox, and progress. When enabled, MacroRunner minimizes before the start
  delay and restores after completion, Stop, or execution failure. This preference
  is saved per device, independently of macro JSON.

The three panels have independent rounded borders, an unobtrusive draggable
splitter gutter, and enforced minimum widths so action fields remain usable.
Panel headings, helper text, and other labels sit on transparent backgrounds
with consistent padding, while the workflow action count uses a rounded badge.
Mouse position pickers and other long inspector buttons span the full form.
Number-field and dropdown arrows have consistent styling in both themes, and
text values align horizontally across text, number and select fields.
Numeric spinboxes apply the inset to their embedded text editor rather than
relying on outer-widget CSS padding, which Qt platform styles handle differently.

Panel widths and window position/size persist between sessions. Use
**View → Dark theme** to switch appearance. The layout resizes and the
properties panel scrolls instead of clipping long action forms.

**View → During screen selection** controls the MacroRunner window while
drawing a region, picking mouse coordinates (start/destination), or sampling
a pixel. Choose **Keep MacroRunner visible**, **Minimize MacroRunner**, or
**Hide MacroRunner** (the default, like a screenshot tool). The editor is
restored automatically after a successful pick, Escape/cancel, or capture
failure, without changing its previous maximized/normal state. If the editor
was already minimized or hidden, it stays that way. The preference is saved
locally and is separate from **Minimize when running**.

## Per-action failure handling

Each executable action has an **On failure** choice in Properties:

- **stop** (default): preserve the existing behavior and stop the workflow.
- **skip**: log the error as an action skip, then continue with the next
  executable action or nested step. Skipping an input action may leave partial
  effects: a click or keystroke may already have reached the application.
- **retry**: offered only for **Wait Until** and **Click Image**. Set
  **retry count** (1–10 additional attempts) and **retry delay** (0–60 seconds).
  The timeout on the action applies **separately to every attempt**. Retry is
  triggered only by a timeout while polling for a condition or image, **before
  any mouse or keyboard input is sent**. The actual image click is never
  retried after an input failure, preventing accidental duplicate clicks.

Retries are finite and honor Pause, Stop, and the existing mouse-corner
fail-safe. A Step executes the whole retry attempt sequence as one action.
Policies are stored in existing version-2 macro JSON, and older macros
automatically default to stop. Run History shows retry attempts, skipped
actions, and safe error categories without logging action parameters.

## Run history and diagnostics

Open **History** in the toolbar (or **View → History**) to see a bounded
timeline of recent workflow runs, including start time, duration, final status,
action indices and structural paths, successful image matches, condition state
changes, and screen-region watcher triggers. Error diagnostics are summarized
without persisting the raw error message or any user-defined action values.

History is stored **locally** in MacroRunner's application data directory,
limited to the most recent 40 runs and 250 diagnostic events per run. Use
**Copy selected details** or **Export safe JSON…** to share redacted diagnostic
metadata; the export omits screen images and raw action parameters. Use
**Clear history and screenshots** to remove saved data.

**Save a screenshot on execution error** is **off by default**. You can enable
it only after acknowledging that a screenshot may contain sensitive content.
When enabled, failed runs store a reduced JPEG screenshot locally, with a
configurable cap of 0–20 saved images (default 5). Screenshots are never
included in the normal JSON export. You can open an explicitly saved
failure image from History or clear all images and records. This does not
change saved macro files and does not require an account or cloud service.

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

For **Watch Region Changes**, select the block and click **Test monitoring…**
in Properties to open a live read-only diagnostic window. It previews the
accepted baseline, the newest screenshot and the changed-pixel mask, along
with the actual measured percentage, threshold, tolerance, confirmation count
and accepted transition count. **Recapture baseline** discards the previous
reference state. **Stop testing** ends screenshot sampling; no nested actions
are executed and unsaved form values are not committed. To avoid detecting the
MacroRunner window instead of the target, enable **Minimize when running**
before opening the tester, and keep its separate preview outside the watched
region. Capture errors include platform-specific guidance.

**Watch Region Changes** monitors a selected rectangle by taking screenshots
at a configurable interval (default 0.5 s). A change triggers its nested
actions when the percentage of pixels differing from the last accepted screen
state reaches the configured threshold for the requested number of consecutive
captures. The watcher pauses while nested actions execute, then retains the
last confirmed state as its baseline: if the region changes again while those
actions run, that change can still trigger the next cycle. Set maximum changes
to 0 to watch until Stop, or choose a finite trigger count. Pausing and Stop
are supported. A new watch block or whole-workflow repeat starts with a new
initial baseline.

For reliable detection, draw a tight region around the changing content.
Small updates may not reach the default 5% changed-pixel threshold in a large
rectangle; lower the percentage for small changes and use confirmations to
filter flicker. **Minimize when running** is separate from the screen-selection
visibility setting. If MacroRunner covers the watched area during playback,
its own UI may be captured instead of the target application.
The screen selection overlay uses Qt global coordinates; on multi-monitor
mixed-DPI systems and restrictive Wayland sessions, screen capture and
coordinates may depend on desktop permissions and display scaling.

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
