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

## Portable workflow packages (Issue #60)

Use **File → Export portable package…** to transfer a workflow to another
computer. MacroRunner creates one **.mrpkg** ZIP file containing a version-2
workflow and **only its referenced images** (Click Image, Wait Until,
If/Else and Repeat Until image conditions, including image-path variable
defaults). Identical images are stored once; images with the same filename
but different content stay separate. Missing, unreadable or oversized images
block export with an actionable message.

Review the confirmation before exporting: **reference images may contain
sensitive screenshots**, and workflow JSON may contain typed text, clipboard
literals, variable defaults or local paths in plaintext. Do not share private
workflows without inspecting them. Image-path variables with no default are
not packaged and must be configured on the destination machine. Other local
file paths, application launch paths and target-window identities are not
portable and may need editing.

On the receiving Windows or Ubuntu computer, choose **File → Import portable
package…**. The importer checks the ZIP's filenames, manifest, entry types,
size limits, image contents and SHA-256 checksums; it does not execute any
actions. Accepted images are copied into MacroRunner's **managed local assets**
directory and references are updated automatically. The imported workflow
opens as an **unsaved copy**; review it, then use **Save** to write ordinary
workflow JSON. Avoid deleting the managed assets directory while workflows
still reference it.

Only .mrpkg uses this ZIP format. The existing **Open/Save** commands continue
to read/write ordinary .json workflows, including legacy action-list files.
MacroRunner does not modify the original source images or the source JSON
when exporting. On a rejected import, staged files are removed without
replacing any existing managed assets.

## Reusable workflow snippets (Issue #59)

Choose one or more sibling actions in the workflow tree, or select a complete
Repeat, If/Else, Repeat Until, or Watch Region Changes group. Click
**Snippets… → Save selection…** and enter a name. Use the search box to find
a saved snippet and preview its actions and variable dependencies.

To insert, select the target workflow item **before** opening Snippets… and
click **Insert copy**. Insertion takes place after a leaf, inside the selected
group's main branch, or into a selected Else branch. With no current tree item
it appends to the workflow. The new actions are editable, draggable and
undoable with one Undo.

Use **Rename…**, **Replace from selection…** (confirmation required), or
**Delete…** to manage snippets. **Import…** reads an exported snippet JSON
into the local library; **Export…** writes a copy for another computer.
Snippets are **copies, not links**: edits to the library never affect an
already inserted workflow, and edits to inserted actions never change the
library. The library lives in MacroRunner's local application-data directory
in a snippets subdirectory, separate from saved workflow JSON files.

Insertion validates complete control groups, variable types and references,
and local image assets. Missing variables are added to the destination workflow,
while existing names keep their original values and must match the type.
**Text variable defaults are omitted** from snippets to avoid copying stored
secrets; configure them or supply run overrides/results as required. Clipboard
action literals may still contain sensitive content, so review them before
saving or exporting. Images are referenced by path, **not bundled**: adjust
image paths after transferring between Ubuntu and Windows. Failed or malformed
imports never modify an open workflow.

## Typed workflow variables and action results (Issue #58)

Use **Variables…** on the toolbar to add up to 100 named workflow variables.
Names are ASCII letters/digits/underscores (starting with a letter or
underscore). Each variable has one declared type: **Text**, **Number**,
**Boolean**, or **Coordinates** (`x,y` integer pixels). Set a typed
**Default** value or check **Unset** to require an earlier action result.
Optional **Use override** sets an ephemeral, local run override. Overrides
apply instead of defaults when starting a run and are **not saved in JSON,
recovery, or Run History**. They remain for the current editor session until
a new workflow is opened/created. Default text (including sensitive text)
**is saved in plaintext** in the macro and local crash recovery.

To use a variable, select an action and choose **Bind ...** in Properties,
then **Apply changes**. Compatible typed variables are listed for supported
fields only. A coordinate variable can replace a full X/Y point for
Click/Move or the source/destination of Drag. Number variables can replace
Wait seconds, Scroll amount, Click Image offsets and image/pixel-condition
coordinates, confidence or timeout. Text variables can provide keyboard
text, clipboard text, local file paths, application paths, image filenames,
and pixel-condition expected colors. If/Else and Repeat Until conditions
can use these bindings when evaluating their current screen probes. Boolean variables can control clipboard restoration
or file overwrite. The entire field is substituted as one typed value;
there is **no template interpolation, Python, shell, or expression engine**.
Incorrect types, undefined names, and invalid resolved action values fail
before performing the action.

**Action results:** Set **Save result in** on Click Image to store the
located image's **center coordinates** in a declared Coordinates variable
(after a successful click). Add **Read clipboard to variable** to capture
current text into a declared Text variable. An empty clipboard yields empty
text; non-text data fails without assigning an output. Clipboard text is
never placed in diagnostics; it can later be used in Paste clipboard/text,
keyboard typing, or another supported whole-field text binding.

Variable values belong to the **current workflow run**. At the start of
**each whole-workflow repeat**, defaults are loaded, overrides applied, and
previous action outputs discarded. Within nested repeat/conditional groups,
outputs remain available until overwritten, or until the whole-workflow
repeat resets. **Run from Selected** starts with defaults/overrides; skipped
producers do not supply outputs. Using an Unset variable before it receives
a result fails safely. Preflight warns about variables that lack a default
or earlier producer and blocks missing/type-incompatible references. Stop
or Skip on failure uses the existing workflow policy.

Variables are optional additional data in the current **version-2**
`settings.variables` document field. Old version-2 macros and legacy
action-list files still open unchanged; unused files have no variable
settings. Variable definitions, bindings and outputs participate in
undo/redo, save/open, and crash recovery. Untrusted macro documents should
not be run simply because variable references are typed.

## Safe local file and folder actions (Issue #52)

Five local filesystem actions are available in the action palette, without
command-shell execution or additional dependencies:

- **File exists:** Check that a regular file currently exists; otherwise fail
  (On failure: Stop or Skip). It does not produce a workflow variable yet.
- **Wait for file:** Poll until a regular file appears, using Timeout and
  Poll interval. A zero-second timeout checks once. Pause suspends polling
  time and Stop interrupts it; useful after an external download/export.
- **Copy file:** Copy one regular local file to an explicit destination path.
  The source stays in place. Existing destinations are **never overwritten**
  unless **Replace an existing destination file** is checked.
- **Move file:** Copy one file to the destination, then **remove the source
  file only after a successful copy**. The existing destination remains
  untouched by default; overwrite requires the same explicit setting.
  This is a Move operation, **not** a general Delete action.
- **Create folder:** Create the specified directory, including missing
  parent directories. Existing real folders are accepted.

The inspector includes **Browse…** buttons for file sources and destinations,
and a folder picker for existing directories. To create a **new folder**,
browse to its parent if desired, then type the new folder name in the path
field. File Wait also accepts manually entered paths for files that do not
exist yet. **Apply changes** saves the settings; editing alone never
performs filesystem operations.

All paths must be **absolute, OS-native local paths** (e.g. Windows
`C:\\Users\\...\\file.txt` or Linux `/home/user/.../file.txt`).
Home-directory `~` expansion is supported. Relative paths, `..` parent
traversal, symlink source files, and symlink destination targets are rejected
for writing actions. Paths can contain spaces and Unicode. The destination
must include a filename; Copy/Move do **not** infer it from a folder path.
Create the destination folder first if missing (using Create folder). No
glob patterns, environment interpolation, scripting, recursive folder
copy/move, or delete action is included in this phase.

**Conflict and failure behavior:** Copy/Move refuse an existing destination
by default. When overwrite is explicitly enabled, MacroRunner stages a
complete copy in the destination folder and commits it with `os.replace`,
so an interrupted write leaves the previous file intact. Without overwrite,
exclusive creation prevents replacing existing files; an interrupted partial
file is cleaned up. Move removes its source **only after** destination
creation succeeds. A failure while removing the source can leave **both**
files present, which must be handled manually. File-operation side effects
already committed before Stop cannot be rolled back; long copies check Stop
between 1 MiB chunks. There is no general-purpose delete operation.

Preflight validates configured paths, warns for missing source files and
current destination conflicts, but does not assume a future file will
already exist when a workflow starts. Disabled actions have no filesystem
side effects. New actions work in existing Repeat/If/Else groups and
Step/Stop without activating windows or requiring a desktop input backend.
Run History records action kinds and generic error categories, **never
the contents of copied or observed files**. Configured filesystem paths
remain in local macro JSON and recovery snapshots (no secret-store feature
is introduced). Later workflow variables (Issue #58) can extend paths
without changing these actions.

## Click Image offsets and point preview (Issue #49)

**Click image** can now click beside a visual landmark instead of its center.
Configure **Image offset X** and **Image offset Y** in the inspector, measured
in **physical desktop pixels** from the center returned by the image matcher:
positive X goes right, positive Y goes down; negative offsets go left or up.
Both default to zero so existing workflows continue clicking the matched
center exactly as before.

Use **Preview click point…** to take a single screenshot with the current
**unsaved** image, confidence, search region and offset settings. The
read-only result reports the matched center, signed offset, final physical
screen coordinates and similarity score. **Preview does not click or apply
changes to the workflow.** If no match is found, or the computed point is
outside the supported screen/target, a clear warning is shown. Move or
minimize overlapping windows before previewing; preview deliberately does
not activate or expose a covered target window.

On playback, the existing OpenCV match and poll/timeout/retry controls are
reused. After the match, MacroRunner adds the offset **once** to the
physical global match center and checks the final point **before clicking**.
For **nonzero offsets**, a negative or out-of-primary-screen click
point is rejected; with a client-relative target window, the offset point
must additionally remain inside the target's client rectangle. With
**zero offsets**, the previous center-click behavior (including any supported
secondary-monitor coordinate conventions) is unchanged. Target movement/focus
after matching is checked, and Stop before click dispatch prevents input.
A missing reference image or match never triggers a click.

**Display limitations:** On Windows and X11 the screenshot/mouse backend
primarily supports the primary screen. A secondary monitor, negative
coordinates, mixed DPI scaling, or inconsistent screenshot and input
scaling may produce out-of-range points; MacroRunner fails safely rather
than guessing. Test on the actual desktop at the intended scaling, and
keep the image and click point within the supported screen/client area.
Wayland remains restricted by the existing global capture/input limits.
No new vision dependency or image-search algorithm is introduced.

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
