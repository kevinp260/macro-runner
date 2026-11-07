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

## Wait for window state (Issue #48)

Add **Wait for window** after launching an application, before typing or
clicking. Choose the state **appears**, **active**, **hidden**, or **closed**;
set a **Timeout** and **Poll interval**. A timeout of 0 checks the current
state once. Polling is cancellable through Stop, and Pause/Step stay
responsive without busy looping. The timeout counts active polling time,
excluding paused intervals.

Select a source in the inspector:
- **Custom:** Click **Choose…** to select a currently visible window. Its
  title/class and handle/process ID are stored with this action. The
  saved identity can follow a renamed window if its handle/PID remain
  stable; a reopened app may match a **unique** exact title/class.
  For a window that does not exist yet, type its **exact title**, and
  optionally its window class, without picking. Duplicate matches are
  an error until you pick a specific window or refine the title/class.
- **Workflow:** Reuse the binding from **Choose window…** on the main
  editor. It does not re-activate that window just to check its status.

**Appears** requires a mapped/visible window. **Active** requires it to
be the foreground window and does not bring it forward automatically.
**Hidden** requires an *existing, enumerated* hidden/minimized/unmapped
window. **Closed** means no matching window remains in the backend's
enumerated top-level windows; if already absent, it finishes immediately.
For hidden, **absence is not treated as success**, avoiding accidental
confusion with a closed app.

Window state checks work on Windows and supported Ubuntu **X11/Xorg**
window managers. X11 relies on `_NET_CLIENT_LIST` and
`_NET_ACTIVE_WINDOW`: some window managers do not preserve unmapped
clients in that list or accurately expose foreground state. In that case
hidden/closed detection may be limited; test it on your actual session.
On **Wayland**, this feature is unavailable and preflight blocks the
action with an explicit message. Running it performs no mouse/keyboard
input and does not need a global input backend.

A workflow may use **Open application** (Issue #47), **Wait for window
(appears)** and then client-relative input (Issue #45). When the saved
workflow target is missing at startup, preflight allows this specific
sequence and delays coordinate validation until that window appears;
it still blocks ambiguous targets or input that would execute before
the wait. Window waits work inside existing Repeat, If/Else and other
workflow blocks without adding a new window-condition expression.
Stop cancels a wait; an already launched app is not killed.

## Open application, file or URL (Issue #47)

Add **Open application / file / URL** from the action palette, then choose a
mode in Properties:

- **Application:** Choose an absolute path to an executable and optionally
  supply arguments, **one argument per line**. Every line is one literal value:
  an argument such as `My Project Folder` needs no surrounding quotes. The
  app starts directly without `shell=True`, a command interpreter, or a
  terminal. On Windows choose an `.exe` or `.com`; on Linux the file must be
  executable (including a script with an executable bit and valid shebang).
- **File:** Choose an existing local file to open in the system's associated
  default app (Windows file association / Ubuntu `xdg-open`). Arguments are
  not applicable.
- **URL:** Enter an `http://` or `https://` URL to open through the
  default browser. Local `file://`, `javascript:`, and other schemes are
  rejected. Arguments are not applicable.

Use **Browse…** for files/executables and **Test launch…** to open the target
using **current unsaved form fields**. Testing performs a real launch, but
does not apply or save your action. Click **Apply changes** to persist it.

Execution preflight checks the target's existence, type, permissions and URL
format before sending input or initiating an app launch. An unconfigured action
can be inserted and edited, but cannot run until its target is configured.
Relative paths are deliberately unsupported, so behavior does not depend on
the current working directory of an installed application. Paths containing
spaces and Unicode work without shell quoting. No command output is captured.

The launch action **requests** an OS start: success does not imply a browser
successfully rendered the page or the launched application is ready for input.
An OS opener can report delayed failure after a request is accepted. A newly
launched process is **not** stopped or killed when the macro Stop button is
pressed. Stop before the action blocks dispatch; a launch already accepted by
the OS cannot be undone. Launch actions don't alter a saved target-window
binding or force its activation. Use the planned wait-for-window action
(Issue #48) if a subsequent step needs to wait for an app window.

This is supported on Windows and Ubuntu/Linux desktops without opening a
terminal. Ubuntu requires `xdg-open` for file/URL associations. Avoid treating
untrusted workflow files as safe to run: an Open Application action can start
any selected executable in your user account.

## Clipboard and paste actions (Issue #46)

Add **Set clipboard text** from the action palette to put literal text on the
system clipboard, including Unicode and multiline content. Empty text clears
clipboard text. **Paste clipboard / text** has two modes: leave its text field
blank to paste the current system clipboard, or enter text to temporarily put
that text on the clipboard and paste it with Ctrl+V. This is useful for
characters and languages not reliably supported by simulated keystrokes.

For temporary text, **Restore previous clipboard text after paste** is enabled
by default. This restores the prior plain text (or empty clipboard) after a
brief 0.2-second delay, **only if the clipboard still contains the text the
action supplied**, reducing accidental overwrites when another app changes the
clipboard. Restoration is best-effort: some slow applications may consume
clipboard data later, and rich/image clipboard formats cannot be restored. If
non-text data is present and restoration is enabled, the action refuses to
replace it; disable restoration only when you intentionally want to replace
that data. With restoration off, temporary text remains on the clipboard.
Pasting the existing clipboard fails clearly if it is empty or contains no
text. Failed clipboard operations do not send the paste shortcut.

Clipboard operations use the existing Qt clipboard on the GUI thread; playback
waits in the worker without freezing the editor and honors Pause/Step/Stop.
The paste shortcut uses regular foreground desktop input. With a target-window
binding, the target must be active or successfully activated before paste;
Wayland and focus restrictions still apply. Linux X11 clipboard ownership is
application-dependent: the content may not survive exiting MacroRunner.

**Privacy:** Literal action text is stored **in plaintext** in workflow JSON,
local crash-recovery snapshots, and potentially on the system clipboard. Avoid
storing passwords or secrets. Workflow cards and Run History do **not** include
clipboard contents by default. If failure screenshots are explicitly enabled,
those screenshots may show pasted content in the destination app. No clipboard
data is transmitted by MacroRunner. Disabling or skipping a clipboard action
avoids its side effects. The planned
**Read clipboard into variable** integration belongs to Issue #58, when
workflow variables are implemented; this PR introduces no new variable system.

## Target-window automation (Issue #45)

Use **Choose window…** in the editor to bind a workflow to a visible application
window. The picker shows its title, class, process ID (if available), client
size, and client-area screen origin. Enable **Client-relative coordinates**
(default for new bindings) to enter or pick action coordinates relative to the
inside of that window; moving the target preserves these offsets. Disable it
to keep absolute desktop coordinates while still targeting a foreground window.
Use **Clear target** to return to ordinary screen-wide automation.

**Activate before input** is on by default. Before input or screen operations,
MacroRunner re-identifies the target using its original handle/PID/class,
falling back to a *unique* exact title/class match when an application restarts.
If the target is closed, ambiguous, resized so an action falls outside its
client area, or cannot become foreground, the workflow fails rather than
sending input to an unrelated window. When activation is off, the intended
window must already be foreground. The target and options are saved with the
workflow in optional version-2 settings and included in local recovery; old
macros without a target behave exactly as before.

Client-relative mode applies to Click/Move/Drag positions, pixel conditions,
image-search regions (the whole client area when none is selected), and Watch
Region Changes. Coordinate and region pickers convert physical screen positions
to client offsets and reject picks outside the target. Images remain reference
files in the existing workflow. Coordinates are **pixels**, not percentages;
resizing can make offsets invalid. Native client geometry is queried again
before each action and each live watcher screenshot; rapid movement during a
single drag or image match may still cause a safe failure or missed input.

**Platform support:** Windows uses native Win32 APIs; Ubuntu **X11/Xorg** uses
the X11/EWMH window-manager protocol (requires an EWMH-capable WM and libX11).
Some desktops/applications may refuse foreground activation. **Wayland is not
supported for target-window enumeration/activation.** This is *foreground*
automation via ordinary global desktop input, **not background injection**.
It does not reliably click or type into covered/minimized windows without
raising them, and cannot bypass OS input/focus restrictions. X11/Windows
multi-monitor negative origins are supported for coordinates, but screenshot
backends may reject negative-origin image/pixel regions; preflight blocks those
scenarios rather than pretending they work. Check DPI/scaling behavior on the
actual desktop (including mixed-DPI monitors) before relying on recorded picks.

## Unsaved changes and crash recovery

MacroRunner marks unsaved changes with an asterisk (`*`) in the window title, including
changes to whole-workflow repeat count and start delay. **New**, **Open** and
**Close** offer **Save / Discard / Cancel** when changes are pending. Cancelling
keeps the current editor intact; canceling the Save As picker also keeps edits.
Opening an invalid or unreadable file does not replace the current workflow.
Normal saves now use an atomic replace so a failed write does not truncate an
existing workflow file.

After an edit, the app writes a **single** local recovery snapshot within
about one second. The complete workflow and playback settings are stored
in `workflow-recovery.json` inside the operating system's
**MacroRunner application-data directory** (Qt AppLocalDataLocation, the same
parent directory used for Run History). Snapshots are written via a private
temporary file and atomic replacement. Each update replaces the prior snapshot;
**no additional history copies** accumulate. A normal Save or explicit Discard
clears the recovery copy. At startup, **Restore** opens the previous snapshot as
an **unsaved copy** (choose a destination using Save), while **Discard recovery**
deletes it. The dialog shows the original file location and snapshot time (UTC).
Recovery **never silently overwrites the user's saved macro**. If the
recovery file is unreadable, the startup prompt offers **Discard** or **Cancel**.
Cancel keeps the damaged file untouched and suspends new autosaves until the
file is removed; Discard explicitly deletes it so autosaves can resume.

**Privacy:** Recovery is local and is not uploaded, but its JSON contains the
actual workflow contents, including typed strings, application paths and image
references, in **unencrypted plaintext**. The temporary file uses user-only
permissions where supported. Protect your device/user account accordingly and
explicitly Discard or Save when no longer needing recovery data. The app holds
at most one snapshot, capped at **10 MB**; regular macro import/save
limits are unchanged. If recovery storage is unwritable, the app warns and leaves the current
edits in memory so you can save them elsewhere.

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

## Breakpoints and slow-motion debugging

Select one or more **executable** workflow actions and press **F9** (or click
**Breakpoint (F9)**). A visible dot marks each breakpoint. On Run or Run
from Selected, MacroRunner **pauses before** the marked action executes.
Use **Resume** to continue normally or **Step** to execute one action
before pausing again. Stop and the global emergency Stop remain available.
A breakpoint inside Repeat/If/Else triggers each time that enabled action
is reached; disabled actions do not trigger it. Structural Repeat/If/Watch
headers are not executable breakpoints.

The **Debug gap (s)** control (0–5 seconds, 0 by default) slows playback
by inserting a cancellable pause **between** executable actions. It is
a local editor preference, not a change to any action delay or saved JSON.
It also applies when stepping, after the first action.

Breakpoint marks are **editor-only**, are not written to macro JSON, and
are cleared when a workflow is reopened or when Undo/Redo rebuilds the tree.
Marks remain on the same tree item during normal property edits and
reordering, and are not automatically copied to duplicated actions. While
MacroRunner is set to minimize during playback, encountering a breakpoint
restores the editor so Resume/Step are accessible; the editor minimizes
again when continuing. OS window focus restoration varies by desktop.

## Pre-run validation

Before **Run**, **Run from Selected**, or **Step**, MacroRunner checks the
applied workflow without sending any input or taking a screenshot. A findings
dialog explains any invalid settings or control blocks, missing/corrupt
reference images, images too large for their search regions, and screen
coordinates or regions beyond the primary display. **Errors block playback**;
**warnings require an explicit Run anyway** confirmation. Select a finding
and click **Go to action** to highlight its position in the workflow tree.

Primary-screen warnings are advisory: a coordinate may intentionally be on
another monitor, and mixed-DPI systems can have different coordinate scales.
Wayland sessions warn about platform limitations on global input/screen capture.
The validator reads referenced images from the same paths used at runtime
(relative paths are interpreted from the current working directory). Disabled
actions and actions before a Run from Selected start do not need their images
to be accessible. This check does not change or save macro JSON.

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
