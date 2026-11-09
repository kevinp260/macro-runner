"""Offline, plain-language help topics for the MacroRunner desktop editor.

All content is bundled with the application. Search uses only local strings.
Keep labels and action IDs aligned with the actual Qt toolbar and palette.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class HelpTopic:
    id: str
    category: str
    title: str
    body: str
    keywords: str = ""


T = HelpTopic

TOPICS = (
    T("start", "Getting started", "What is MacroRunner?", """
MacroRunner lets you make a list of instructions for your computer to follow.
Each instruction is an **action**: click somewhere, type text, wait for a
window, check for an image, and so on. The list is called a **workflow**.

You build the workflow on the main screen. **Nothing runs while you are
editing it.** Press **Run** when you are ready to try it.

**Start with a harmless test**, such as opening a text editor and typing
a short message. Avoid real purchases, passwords, and destructive file
operations while learning.
""", "automation macro beginner overview"),

    T("using-help", "Getting started", "How to use this Help guide", """
Open **Help → User Guide…** or press **F1** from MacroRunner.
Keep the window open next to the workflow editor while you work.

- Type a word or a short question into **Search the Help guide…**.
  Results update immediately, without using the internet.
- Use the chapter dropdown to look through **Getting started**,
  **Editing workflows**, **Running and debugging**, **Common settings**,
  **Action reference** and **Troubleshooting**.
- Click a topic on the left to read the explanation on the right.
- Clear the search box to see all topics again.

To understand an action you already added, select it in the workflow and
choose **Help → Help for selected action…**.
""", "help search guide index chapters find buttons"),

    T("about", "Getting started", "About MacroRunner and app version", """
Choose **Help → About MacroRunner** to see the **installed app version**
and a link to the project's repository.

The **User Guide (F1)** explains how to use the app; **About** identifies
the build you have installed. The version is useful when reporting an
issue or checking whether an update was installed successfully.

About does not run a workflow, change settings or check for updates.
""", "about version update installed build repository support"),

    T("first-workflow", "Getting started", "Make your first workflow", """
1. Open a harmless app such as a text editor.
2. In MacroRunner's **Actions** panel on the left, double-click
   **Press / Type** to add it.
3. Select the new action in the middle **Workflow** panel.
4. On the right under **Properties**, choose **Type** and enter a test sentence
   in **Keys**, then click **Apply changes**.
5. Choose a suitable **Start delay**, such as 3 seconds. Return focus to
   the text editor before the delay ends.
6. Press **Run** (F5). MacroRunner checks the workflow and starts it.

**Tip:** Select a target window first if you want MacroRunner to verify that
the right application is in front before sending input. The text goes to the
application that actually receives keyboard input.
""", "tutorial new create example beginner type text"),

    T("tour", "Getting started", "Where is everything on the screen?", """
- **Left — Actions:** The available instructions. Search here to find an
  action to add. Double-click or drag an action into the workflow.
- **Middle — Workflow:** Your action list. Select an action to edit it,
  drag to reorder it, and expand or collapse groups.
- **Right — Properties:** Settings for the selected action. Remember to click
  **Apply changes** when you edit a value.
- **Top toolbar:** New, Open, Save, Variables, Snippets, Run, Pause,
  Stop, Step, Run from selected, Breakpoint, History, Record, Undo, Redo.
- **Below the workflow:** Duplicate, Delete, Enable / Disable,
  Collapse all, Expand all, and Breakpoint (F9).
- **Bottom:** Target window, Repeat count, Start delay, Debug gap,
  Minimize when running, progress, and status.
- **Menu bar:** File, Edit, View and Help.

If a word is unfamiliar, type it into this Help search box.
""", "layout navigation find toolbar panels controls buttons"),

    T("example-safe", "Getting started", "Example: click a button after it appears", """
Imagine an app with a **Continue** button that appears after loading.

1. Add **Wait until** and choose an image of the Continue button.
2. Add **Click image** using a small screenshot of that same button.
3. Add **Wait** for a short delay if the next screen needs time.
4. Preview the image match first, then try **Run**.

This is usually safer than clicking at a fixed X/Y point because the button
may move. Image matching still needs the button **visible and unobstructed**.
A workflow will not automatically see a button hidden behind another window.
""", "tutorial example screenshot button image wait until click"),

    T("shortcuts", "Getting started", "Keyboard shortcuts", """
- **F1** — Open the searchable Help guide.
- **F5** — Run the whole workflow.
- **F6** — Pause or resume playback.
- **F9** — Add or remove a breakpoint on selected executable actions.
- **Esc** — Stop playback or an active recording/preview; also cancels
  screen-region selection where applicable.
- **Ctrl+N / Ctrl+O / Ctrl+S** — New / Open / Save workflow.
- **Ctrl+F** — Find / Replace actions inside the workflow.
- **Ctrl+R** — Start or stop recording.
- **Ctrl+Z / Ctrl+Y** — Undo / Redo.
- **Ctrl+D / Delete** — Duplicate / Delete selected workflow actions.
- **Ctrl+Alt+Shift+F6 / F8** — Optional system-wide Pause / Stop hotkeys.
  These depend on OS permissions and may be unavailable.

Other buttons, including **Step** and **Run from selected**, are in
the top toolbar.
""", "hotkeys keyboard f1 f5 f6 f9 control keyboard shortcuts"),

    T("palette", "Editing workflows", "Actions panel and its search", """
The left-hand **Actions** panel is the catalog of instructions you can add.
Type in **Search actions…** to filter the catalog by action name.
Double-click an entry to insert it, or drag it into the middle workflow.

This search looks for **new action types to add**. To find actions that are
**already in your workflow**, use **Edit → Find / Replace… (Ctrl+F)** instead.

Some actions create a complete group with sample child steps. Edit or remove
those sample steps before you run the workflow.
""", "left panel search actions double click drag"),

    T("workflow-tree", "Editing workflows", "Workflow panel: order, groups and selection", """
The middle panel is the list of actions that run in order. Drag a leaf action
to change its place. A group, such as **If / Else**, can contain other
actions. Use the arrow next to a group to expand or collapse it.

Select one action to edit its **Properties**. Use Ctrl-click or Shift-click
to select more than one action for some editing commands. Deleting or
reordering a whole group also affects its children. MacroRunner checks group
structure and rejects invalid moves.

**Collapse all** hides the children for easier reading; **Expand all**
shows them again. Neither changes what will run.
""", "middle sequence collapse expand reorder drag nested tree"),

    T("properties", "Editing workflows", "Properties panel and Apply changes", """
Select an action in the middle panel. Its settings appear on the right:
coordinates, text, waiting time, confidence, and other options depending on
the action.

**Changing a text box does not save the change immediately.**
Click **Apply changes** to update the workflow. Then use **Save** to write
the workflow to a file.

Some read-only previews, such as **Preview click point…** and
**Live OCR preview…**, use what is currently in the form, even before
you click Apply. **Test launch… really starts** the selected application,
file, or URL, so use it carefully.
""", "inspector settings edit apply unsaved draft"),

    T("edit-buttons", "Editing workflows", "Duplicate, Delete, Enable, Collapse and Expand", """
These buttons sit below the workflow list:

- **Duplicate** makes a separate copy of the selected action or group.
- **Delete** removes selected actions. Ctrl+Z can undo the edit.
- **Enable / Disable** switches whether selected executable actions run.
- **Collapse all / Expand all** only changes how much of each group you see.
- **Breakpoint (F9)** marks selected executable actions for debugging.

There are equivalent Duplicate and Delete commands in the **Edit** menu.
Select the intended action first. Structural group markers cannot be
disabled like ordinary actions.
""", "toolbar bottom editing copy remove group toggle"),

    T("enabled", "Editing workflows", "Enabled and disabled actions", """
An **enabled** action will run when the workflow reaches it. A **disabled**
action stays in the workflow but is skipped.

You can uncheck the small box next to an action, use the
**Enable / Disable** button, or change **Enabled** in Properties.

Disabled actions appear crossed out. Use this when you want to test part
of a workflow without deleting steps. A group itself is structural; enable
or disable the actions inside it.
""", "checkbox skip disable muted crossed out"),

    T("undo", "Editing workflows", "Undo and Redo", """
**Undo (Ctrl+Z)** reverses a recent edit to the workflow.
**Redo (Ctrl+Y)** puts an undone edit back.

Examples: accidentally deleting an action, changing a coordinate, inserting
a snippet, or bulk-replacing several values. A completed bulk replacement
counts as **one Undo step**.

Undo is for **editor changes**. It cannot undo something that already
happened in another application, such as a mouse click, sent message,
copied file or launched program.
""", "history edits revert restore changes"),

    T("find-replace", "Editing workflows", "Find / Replace actions (Ctrl+F)", """
Choose **Edit → Find / Replace… (Ctrl+F)**. This searches actions you have
already added, even inside collapsed groups. Search by type, name, enabled
state, keyboard value, coordinates, or image filename.

Click a match to jump to the action. For bulk changes, choose a supported
text or numeric property, type the new value, and press **Preview changes**.
Inspect the old/new values before pressing **Apply changes**.

Group markers, action types, variable bindings and unrelated values are
protected. Some incompatible actions are skipped. A valid bulk update
can be reverted with **one Undo**.
""", "find search existing actions change multiple replace text numeric"),

    T("new-save-open", "Editing workflows", "New, Open and Save", """
- **New (Ctrl+N)** starts a new empty workflow.
- **Open (Ctrl+O)** loads an existing workflow file, normally a .json file.
- **Save (Ctrl+S)** saves the current workflow. On the first save, you choose
  a filename.

A star (*) in the window title means there are unsaved changes.
MacroRunner asks whether to **Save**, **Discard** or **Cancel** when you
try to leave an edited workflow.

A saved workflow is a set of instructions. **Opening it does not execute it.**
Review workflows received from other people before choosing Run.
""", "files new open save json unsaved dirty star"),

    T("recovery", "Editing workflows", "Crash recovery and unsaved work", """
MacroRunner keeps a local recovery copy of unsaved workflow changes.
If the application closes unexpectedly, you may be asked whether to
**Restore** or **Discard** the recovery.

Restoring opens an **unsaved copy** so you can inspect it and choose Save.
Recovery is a safety net, not a substitute for saving your workflow.
It may include the text you typed into actions or variable defaults.

If you discard a saved change accidentally, Undo may help while that
editor session is still open. It cannot undo a past run in another app.
""", "crash restore backup snapshots recovery privacy"),

    T("variables", "Editing workflows", "Variables: reusable values", """
Click **Variables…** on the top toolbar to create a named value.
For example, make a number called delay_seconds or a coordinate called
button_position, then use **Bind…** in an action's Properties.

Variables can hold **Text, Number, Boolean (true/false), or Coordinates**.
Each can have a default value. A run-only **override** temporarily changes
that value without saving it to the workflow.

Some actions can save an output to a variable, such as image-click center
coordinates or clipboard text. Values reset at the start of each full
workflow repeat. Text defaults are saved in plain text, so do not store
passwords in shared workflows.
""", "variables bind typed value reuse output defaults overrides"),

    T("snippets", "Editing workflows", "Snippets: reusable action groups", """
Click **Snippets…** to save a selected action or complete group under a
name. You can later insert a **copy** into the same or another workflow.

For example, save a sequence that waits for a window, clicks a button,
and types a label. The inserted copy is **independent**: changing the
saved snippet later does not change previously inserted copies.

The snippet library is stored locally. You can rename, replace, delete,
import, or export snippets. Snippets reference image filenames but do
not include image files automatically.
""", "templates save selection reused library insert copy"),

    T("packages", "Editing workflows", "Import / Export portable package (.mrpkg)", """
In **File**, choose **Export portable package…** to create a .mrpkg file.
It includes your workflow and the reference images it uses, making transfer
to another computer easier.

On the receiving computer choose **Import portable package…**. MacroRunner
checks the package and opens it as an **unsaved copy**. Review the steps
and save it locally before running it.

Regular **Open / Save** uses .json instead. A portable package does not
make every local file path, application path, or target window valid on
the new computer. Packages and screenshots can contain sensitive information.
""", "zip portable import export transfer share images assets"),

    T("window-target", "Editing workflows", "Target: Screen or a selected window", """
At the bottom of the editor, **Target: Screen (absolute)** means mouse and
keyboard actions use the normal desktop. Click **Choose window…** to select
an application window instead. **Clear target** returns to screen mode.

With **Client-relative coordinates**, X=0 and Y=0 start at the target
window's client area, rather than the desktop corner. MacroRunner updates
the position if the window moves. **Activate before input** tries to bring
the target to the front when needed.

**Important:** this does NOT send clicks or typing to a fully hidden
background window. The target must become the foreground window before
input; otherwise the action is blocked to avoid affecting the wrong app.
Windows and Ubuntu X11 support this more fully than Wayland.
""", "window picker select focus foreground activate behind background relative"),

    T("screen-selection", "Editing workflows", "During screen selection: Show, Minimize or Hide", """
Use **View → During screen selection** to decide what happens to MacroRunner
while you pick a pixel, coordinate, or rectangle.

- **Keep MacroRunner visible:** the editor stays on screen.
- **Minimize MacroRunner:** it moves to the taskbar/dock.
- **Hide MacroRunner:** it disappears temporarily so it will not block the
  part of the screen you want to select. This is the default.

After selection or cancellation, the editor normally returns to its former
state. This setting is different from **Minimize when running**, which
controls what happens during playback.
""", "view selection capture pick coordinate hide minimize"),

    T("appearance", "Editing workflows", "View, dark theme and layout sizes", """
Choose **View → Dark theme** to switch appearance. Drag the dividers between
the three main panels to give more space to Actions, Workflow or Properties.
The properties panel scrolls if its settings do not fit.

The editor remembers window size, panel widths, and some display preferences
on this computer. These are not instructions inside your workflow.
""", "theme light dark display splitter resize layout settings"),

    T("run", "Running and debugging", "Run (F5): execute your workflow", """
Press **Run (F5)** to execute your workflow from the beginning.

Before running, MacroRunner performs a **preflight check** to find problems
such as missing images or invalid values. It then waits for the configured
**Start delay** and performs enabled actions in order, following any loops
or conditions. **Repeat** controls how many full-workflow passes to make.

For a safe first test, use a text editor, a short workflow, and a start
delay long enough to move focus to the right application.
""", "play start execution f5 workflow"),

    T("run-selected", "Running and debugging", "Run from selected", """
Select an action in the workflow and press **Run from selected** in the top
toolbar. MacroRunner starts there rather than at the first action and uses
**one full-workflow pass** for this special run.

This is helpful when testing a later part of a long workflow.
It does **not run earlier actions**. If a previous action was supposed to
create a variable value, file, or window, the selected part may fail.
You also cannot start in the middle of a structural control block.

**Example:** skip the first three setup clicks and test the later
Wait for window step.
""", "run from selected partial start position"),

    T("pause", "Running and debugging", "Pause, Resume and Stop", """
**Pause (F6)** suspends playback at a safe point. The button changes to
**Resume**; press it again to continue. A pause cannot undo an input that
was already sent.

**Stop (Esc)** requests cancellation. An action already accepted by the OS,
such as launching another app, might not be reversible. MacroRunner attempts
to release keyboard keys it is holding when execution ends.

A global Stop shortcut (**Ctrl+Alt+Shift+F8**) may work while another
window has focus, depending on your OS and permissions. Always test
automatic input with a harmless destination first.
""", "stop cancellation resume halted f6 esc emergency"),

    T("step", "Running and debugging", "Step: run one action at a time", """
**Step** lets you inspect the workflow during debugging rather than
running continuously.

1. Select the action where you want to begin, or start from the beginning.
2. Press **Step**. Playback starts in a paused debugging mode.
3. Press **Step** again whenever you want to allow the next executable
   action to proceed.
4. Use **Resume** to continue normally, or **Stop** to cancel.

If the workflow contains loops, conditions or waits, the next action
depends on which branch the workflow takes. This is different from
**Debug gap**, which adds a fixed delay but does not stop for your input.
""", "debug step slow single action manual walkthrough"),

    T("breakpoint", "Running and debugging", "Breakpoint (F9): pause at a chosen action", """
A **breakpoint** is a temporary stop sign you put on an action when you
want to inspect what happens before it runs.

**Example:** your workflow fills out a form and then clicks Submit. Select
the Submit action and press **Breakpoint (F9)**. When playback reaches it,
MacroRunner **pauses before that click**. You can check the form, then
choose **Step** to run the action or **Resume** to continue.

A marked action shows a dot in the workflow. Select it and press F9 again
to remove the breakpoint. Breakpoints can be set on executable actions,
not whole structural groups. They are **editor-only** and are not saved
in your .json workflow. A loop may encounter the same breakpoint again
on its next pass.
""", "debugging break point stop sign f9 pause inspect watch"),

    T("debug-gap", "Running and debugging", "Debug gap (s): slow down actions", """
**Debug gap** is the small number field at the bottom of the editor, next
to **Start delay (s)**.

It adds an **extra pause between executable actions** so you can see what
MacroRunner is doing. For example, a Debug gap of **1.0** adds one second
between actions. Set it to **0** for no extra delay.

Use it when a macro runs too quickly to observe. It is a debugging aid,
**not a guaranteed wait for an application to finish loading**. For loading
screens, use **Wait for window**, **Wait until**, **Wait for text** or
another condition instead.

Debug gap is saved as a **preference on this computer**, not inside the
workflow file. Unlike **Breakpoint**, it does not require you to press
Resume for every action.
""", "debugging gap slow playback between actions seconds footer delay"),

    T("start-delay", "Running and debugging", "Start delay (s)", """
**Start delay** is the number of seconds MacroRunner waits **before** it
starts executing actions after you press Run. The default is 3 seconds.

It gives you time to move to the other application or make sure the
correct window has focus. It is **not** added between every action.

For delays between steps, use a **Wait** action or **Debug gap**.
For something that may finish at an unpredictable time, use a conditional
wait such as **Wait until**.
""", "timer countdown initial launch before start bottom settings"),

    T("repeats", "Running and debugging", "Repeat count: repeat the whole workflow", """
The **Repeat** number at the bottom says how many times to run the **entire
workflow** when you press Run.

**Example:** Repeat = 3 makes MacroRunner go through the whole workflow
three times. A **Repeat block** inside the workflow is different: it
repeats only the actions inside that block.

A Run from selected or Step session starts with one overall pass.
Whole-workflow repetition resets workflow variables to their
defaults/overrides at the start of each pass.
""", "loop cycles footer whole repeat count"),

    T("minimize-run", "Running and debugging", "Minimize when running", """
Check **Minimize when running** at the bottom to move MacroRunner out of
the way when playback starts. The editor normally restores itself when the
run ends or fails.

If a **breakpoint** pauses the workflow, MacroRunner can temporarily show
the editor so you can choose Step or Resume.

This is a computer-specific display preference. It does **not** make an
occluded app receive background clicks: the target still needs focus and
a visible area.
""", "hide app when playback starts taskbar minimize restore"),

    T("preflight", "Running and debugging", "Preflight: checks before a run", """
When you press Run, MacroRunner checks the workflow **before sending input**.
It may detect a missing reference image, invalid action settings, missing
variable, impossible region, or unsupported target window.

**Errors** prevent the run. **Warnings** are things to review, such as a
screen region that may be off-display; you can decide whether to proceed.
Some problems can only be discovered at runtime.

If preflight points to an action, select or navigate to that action and fix
its Properties. A successful preflight does not guarantee the external app
will behave as expected.
""", "validation warnings errors can't run blocked"),

    T("failure", "Running and debugging", "On failure: Stop, Skip or Retry", """
In an action's **Properties**, **On failure** controls what happens if
the action cannot complete.

- **Stop** (default): stop the workflow and report the error.
- **Skip**: continue with the next action. Use with care because a later
  action may depend on this one.
- **Retry**: try the failed detection again after a delay. This is available
  only for supported **pre-input detection** actions, such as Click image,
  Wait until and Wait for text. It is not a general retry for typing,
  launching apps, or moving files.

**Retry count** means extra attempts; **Retry delay** is the time between
attempts. Skipping a failed click or keystroke does not undo it.
""", "failure policy timeout skip retry attempts delay settings"),

    T("history", "Running and debugging", "History: see what happened during a run", """
Click **History** on the top toolbar to see past runs, their outcomes,
and where execution failed or paused. It can help you understand why a
workflow stopped.

The normal run history is kept **locally** and avoids saving typed text,
clipboard values or action parameters. History is different from **Undo**:
Undo reverts editor changes, while History describes **runs**.

The History window also lets you clear records or export redacted
information for troubleshooting.
""", "diagnostics logs run errors inspect completed"),

    T("screenshots", "Running and debugging", "Failure screenshots (optional and sensitive)", """
In **History**, you may optionally enable **Save a screenshot on execution
error**. It can help diagnose why an image or screen action failed.

This feature is **off by default** because screenshots may contain private
messages, passwords, or documents. Captures are kept locally, with a limit,
and can be removed when you clear history.

Only enable it while testing harmless content. Normal history does not
store screenshots.
""", "capture error screenshot privacy diagnostics"),

    T("record", "Running and debugging", "Record: capture mouse and optional keyboard actions", """
Press **Record (Ctrl+R)** to make actions by using your mouse. Recording
begins after a short countdown. Press **Stop recording** when finished.

In the recording settings you can choose whether to insert waits between
captured actions, set a minimum wait, and choose click repeat counts.
Keyboard recording is **optional** and must be enabled separately.

**Privacy warning:** keyboard recording can capture passwords or other
sensitive text typed into another application. Only test it with harmless
sample input. Recording does not automatically make a perfect workflow:
review the captured actions and edit them before running.
""", "recording capture events mouse key privacy countdown"),

    T("hotkeys", "Running and debugging", "System-wide Pause and Stop hotkeys", """
Where supported, these shortcuts can work while another application is
in front:

- **Ctrl+Alt+Shift+F6** — Pause or resume.
- **Ctrl+Alt+Shift+F8** — Stop.

They depend on desktop permissions and may not work in all Linux or Windows
environments. The regular **Pause (F6)** and **Stop (Esc)** controls are
available in the MacroRunner window.

Test emergency stopping before running a long workflow that sends input.
""", "global shortcuts emergency safety f6 f8"),

    T("coordinates", "Common settings", "Coordinates, regions and offsets", """
**X** is the horizontal position; **Y** is the vertical position.
A point such as (100, 200) means 100 pixels across and 200 pixels down
from the screen's origin, unless you enabled client-relative window mode.

**Pick start (3 s)** captures the mouse position after three seconds.
**Pick destination** does the same for Drag. **Test position** moves the
pointer there without clicking. A **region** is a rectangle defined by
X, Y, width and height, often picked with **Draw screen region…**.

**Image offsets** move a click away from the center of the matched image:
positive X moves right and positive Y moves down. Multi-monitor and
display scaling may affect physical coordinates; test on your desktop.
""", "x y screen pixels location position region width height click offset"),

    T("conditions", "Common settings", "Image matching, pixel checks and confidence", """
A **reference image** is a small screenshot of what should appear on
screen, such as a button. **Confidence** controls how similar the visible
image must be to count as a match. A higher number is stricter.

A **pixel** condition checks one screen point against a color such as
#00FF00 (green). **Pixel tolerance** allows slight color differences.
**Sample pixel (3 s)** captures a point and color for you.

**Matches** means continue when the image/color is present;
**not_matches** means continue when it is absent. A screen region limits
where an image is searched. If a window covers the target, MacroRunner
generally cannot see the hidden image.
""", "confidence screenshot region image pixel color source tolerance matches"),

    T("wait-settings", "Common settings", "Timeout and poll interval", """
**Timeout** is how long an action may keep waiting. **Poll interval** is
how often it checks again.

For example, Timeout = **10 seconds** and Poll interval = **0.5 seconds**
means check roughly twice per second, stopping successfully if the condition
becomes true, or failing after about ten seconds.

A very small interval can use more CPU. A very short timeout may fail
before an application finishes opening. For waiting on an external app,
prefer **Wait until** or **Wait for window** over an arbitrary fixed delay.
""", "timing poll frequency condition seconds check every"),

    T("variable-binding", "Common settings", "Bind a field to a variable", """
When an action supports variables, Properties may show a **Bind…** dropdown.
Choose a compatible variable to supply that entire field at runtime instead
of its fixed value.

For example, bind **Wait seconds** to a Number variable or Click X/Y
to a Coordinates variable. If no compatible variable is defined,
the binding dropdown may not appear.

Bindings do not perform calculations or replace part of a sentence.
Missing or incorrectly typed variable values cause validation or runtime
errors instead of silently using another value.
""", "bind dynamic parameter field replace default variable"),

    T("window-mode", "Common settings", "Window wait states and focus", """
**Wait for window** has four states:

- **Appears:** a matching window exists.
- **Active:** it is the front/foreground window.
- **Hidden:** it is minimized or otherwise marked hidden by the window manager.
- **Closed:** it is no longer found.

You can enter an exact window title, pick an existing window, optionally
narrow it by window class, or reuse the workflow's configured target.
A window merely **appearing** does not mean it is ready for typing.
Use an additional screen/image condition if needed.
""", "open closed hidden active title foreground handle pid"),

    T("ocr", "Common settings", "Text recognition (offline OCR)", """
**Find text** and **Wait for text** look for written words in a screenshot.
They require the separately installed **Tesseract OCR** engine and the
selected language pack (for example, eng for English).

Find text can check once and optionally click the recognized phrase's
center. To avoid clicking the wrong thing, a click is blocked if the phrase
is found multiple times. Wait for text polls until the phrase appears.

Try **Live OCR preview…** to see what it detects without clicking.
Prefer a small region and clear, high-contrast text. Recognition is
local; screenshots and recognized text are not sent to a cloud service.
""", "tesseract image text reading OCR find wait language"),

    T("watch-settings", "Common settings", "Watch region: change percentage and confirmations", """
**Watch region changes** looks for a meaningful change inside a selected
rectangle, such as a notification appearing.

- **Changed pixels %** is how much of the region must change to count.
- **Pixel tolerance** ignores tiny color differences.
- **Confirmations** means how many consecutive checks must agree before a
  change is accepted.
- **Poll interval** controls how often the region is checked.
- **Maximum changes** limits how many changes to act on; 0 means keep
  watching until Stop.

Use **Test monitoring…** to preview the baseline, latest capture, and
difference mask without executing the child actions. Use **Recapture
baseline** to reset what counts as the unchanged screen.
""", "watch pixel sensitivity region baseline tester flicker animation"),

    T("action-click", "Action reference", "Click", """
Sends a mouse click to a chosen X/Y coordinate. Choose left, right, or
middle button; set how many clicks to make and the interval between them.

**Example:** click the Search field at (300, 250).

**Where:** Actions → Click; set X/Y under Properties.
Use **Pick start (3 s)** to capture a point and **Test position** to
move the pointer there without clicking.

A fixed coordinate may become wrong if the window moves. Use **Click image**
when the target's position can change.
""", "mouse click coordinate fixed button"),

    T("action-click_image", "Action reference", "Click image", """
Looks for a reference image currently visible on screen and clicks its
center when it finds a strong enough match.

**Example:** click a small Save button screenshot rather than guessing
its X/Y position.

When adding Click Image, choose **Browse…** to use an existing reference
image or **Capture…** to draw a rectangle and save a new screenshot.
You can change the reference later in Inspector; click **Apply changes**
to keep subsequent edits. **Draw screen region…** controls
where to search for the reference; it does not capture the reference itself.

Adjust **Confidence** and optional search region, then use **Preview click
point…** before running. X/Y offsets shift the click away from the match
center. A timeout allows time to find it.

A visible match is required; a covered or redesigned button may not match.
""", "find screenshot locate click photo match center offset"),

    T("action-wait", "Action reference", "Wait", """
Does nothing for a fixed number of seconds before continuing to the
next action.

**Example:** wait 2 seconds after opening a menu.

**Where:** Actions → Wait; enter Seconds in Properties.
For a page that can load quickly or slowly, a condition-based **Wait until**
or **Wait for window** is more reliable than an arbitrary delay.
""", "sleep delay seconds pause fixed"),

    T("action-wait_until", "Action reference", "Wait until", """
Keeps checking the screen until an **image** or **pixel color** matches
(or stops matching), or until Timeout is reached.

**Example:** wait until a loading spinner disappears before clicking.

Choose **Condition source** (image or pixel), **Match mode** (matches or
not_matches), and **Timeout / Poll interval**. A timed-out action follows
its **On failure** policy. It does not send a click by itself.
""", "condition wait image pixel disappear timeout polling"),

    T("action-find_text", "Action reference", "Find text (offline OCR)", """
Checks the visible screen **once** for a word or phrase using the
separately installed local Tesseract OCR engine.

**Example:** check whether the words "Sign in" are visible.

Choose the phrase, language, minimum confidence and optional search
region. You may enable **Click center of recognized phrase** for an
optional click only when one confident match is found. Use **Live OCR
preview…** first. No cloud service is involved.
""", "read letters words recognition tesseract click text"),

    T("action-wait_text", "Action reference", "Wait for text (offline OCR)", """
Keeps checking for words on screen until the requested phrase appears or
the time limit runs out. Requires local Tesseract and the language pack.

**Example:** wait until a status label says "Ready" before continuing.

Set the phrase, confidence, region, Timeout and Poll interval.
Unlike **Find text**, this action does not click.
""", "text waiting OCR tesseract phrase ready status"),

    T("action-key", "Action reference", "Press / Type", """
Sends a key press, keyboard shortcut, or a piece of text.

**Example:** choose **Press** and enter ctrl+s to save in the active app.
Or choose **Type** and enter a sample sentence for a text field.

The target app must have keyboard focus. For Unicode or multiline text
that does not type reliably, use **Paste clipboard / text** instead.
""", "keyboard input press type shortcut ctrl+s"),

    T("action-key_down", "Action reference", "Hold key", """
Presses a key down and leaves it held until a later **Release key** action.

**Example:** Hold key: shift; then send another key; then Release key: shift.

Use with care: the computer may behave as if that key is still pressed
between actions. MacroRunner attempts to release held keys when a run
stops or finishes.
""", "key down modifier hold shift control"),

    T("action-key_up", "Action reference", "Release key", """
Releases a key that was previously held by **Hold key**.

**Example:** after Hold key: shift and a click, add Release key: shift.

It is good practice to pair hold and release actions. Stopping a macro
also attempts to release keys the workflow holds.
""", "key up let go modifier shift"),

    T("action-move", "Action reference", "Move mouse", """
Moves the pointer to an X/Y point without clicking.

**Example:** move the mouse over a menu so its hover options appear.

Enter the point and **Move duration**. You can capture a point with
**Pick start (3 s)** and check it with **Test position**.
""", "pointer cursor hover coordinate movement"),

    T("action-scroll", "Action reference", "Scroll", """
Scrolls the mouse wheel by a specified number of steps.

**Example:** scroll down to reveal an item farther down a web page.
A negative amount usually scrolls down; a positive amount scrolls up.

Make sure the correct window is in front and the pointer is over the
area that should scroll.
""", "mouse wheel up down page"),

    T("action-drag", "Action reference", "Drag", """
Holds a mouse button while moving from a start point (X/Y) to a destination
(to X/to Y), then releases it.

**Example:** move an item from one folder area to another.

Set the button and **Move duration**. Use **Pick start** and
**Pick destination** to capture both points. Try the action on harmless
items first, as a drag can move or rearrange real content.
""", "drag and drop pointer start destination"),

    T("action-clipboard_set", "Action reference", "Set clipboard text", """
Places text in the computer's clipboard. It does not paste into another
application by itself.

**Example:** put a standard greeting on the clipboard so a later step
can paste it.

Enter the text under Properties. The text is stored in the workflow
file, so avoid including passwords or other private values.
""", "copy clipboard write text"),

    T("action-clipboard_paste", "Action reference", "Paste clipboard / text", """
Pastes into the active application using the clipboard.

Leave the action's text blank to paste whatever is already on the
clipboard, or enter custom text to paste that instead. With custom
text, **Restore previous clipboard text after paste** tries to restore
the previous plain-text clipboard value if no other app changed it.

**Example:** paste a multiline address into a form. The destination
must already have focus.
""", "paste ctrl+v unicode multi line restore"),

    T("action-clipboard_read", "Action reference", "Read clipboard to variable", """
Reads the current **plain text** from the clipboard and saves it to a
declared Text variable.

**Example:** copy a value in one app, then reuse it in a later
Paste clipboard / text action bound to that variable.

Create a Text variable first and choose it under **Save result in**.
Non-text clipboard content cannot be read by this action.
""", "clipboard get text variable output"),

    T("action-launch", "Action reference", "Open application / file / URL", """
Requests the operating system to open an application, file, or web address.

**Example:** open a local text editor or an https:// web page.

Choose **Application**, **File**, or **URL** in Properties. Application
arguments are literal values, one per line, not shell commands.
**Browse…** helps select local paths. **Test launch…** actually opens the
target; it is not just a preview.

An opened application might not be ready immediately. Add **Wait for
window** or a screen check afterward. Do not run untrusted workflows that
launch executables.
""", "start program browser URL executable files launch"),

    T("action-wait_window", "Action reference", "Wait for window", """
Waits for an application window to **appear**, become **active**, become
**hidden**, or be **closed**.

**Example:** open an app, then wait for its window to appear before typing.

Select a known window with **Choose…**, enter its exact title and optional
class filter, or reuse the workflow's target window. Set Timeout and
Poll interval. This action **observes** window state; it does not
automatically click or type.
""", "window waits appears active hidden closed title"),

    T("action-file_check", "Action reference", "File exists", """
Checks whether a regular file exists at a path on your computer.

**Example:** make sure an exported CSV file is present before continuing.

Enter the complete file path or use Browse. If the file is missing,
the action follows **On failure** (Stop or Skip). It does not wait
or create the file.
""", "check filesystem present path exists"),

    T("action-file_wait", "Action reference", "Wait for file", """
Waits until a specific regular file appears at a path.

**Example:** wait for a program to finish creating an export file.

Set File path, Timeout and Poll interval. A timeout of zero checks once.
This action does not download or create the file itself.
""", "wait for download export filesystem timeout"),

    T("action-file_copy", "Action reference", "Copy file", """
Copies one local file from a source path to a destination path.
The original stays where it is.

**Example:** copy a generated report into a backup folder.

The destination is **not overwritten by default**. Check
**Replace an existing destination file** only when you deliberately
want to overwrite something. Review paths carefully.
""", "duplicate file filesystem source destination overwrite"),

    T("action-file_move", "Action reference", "Move file", """
Moves one local file to a new destination. The source is removed
only after the new copy succeeds.

**Example:** move a completed export into an Archive folder.

An existing destination is protected unless you explicitly enable
overwrite. This is **not** a general delete-file instruction.
""", "rename relocate file source destination archive"),

    T("action-folder_create", "Action reference", "Create folder", """
Creates a directory if it does not already exist. Missing parent folders
can be created too.

**Example:** create a Reports/November folder before copying a file into it.

Enter the desired folder path. Browse can help choose an existing parent,
then you can type the new folder name. This action does not delete folders.
""", "mkdir directory make folders"),

    T("action-loop_start", "Action reference", "Repeat block", """
Repeats the **actions inside this group** a fixed number of times.

**Example:** click Next and wait, five times in a row.

Select the Repeat block in the workflow, choose the repeat count, and put
the steps you want repeated inside it. This is different from the
**Repeat** field at the bottom, which repeats the **entire workflow**.
""", "loop for count repetitions group cycles"),

    T("action-if_start", "Action reference", "If / Else", """
Makes a decision using what is visible on screen.

**Example:** If a warning icon appears, press Cancel; otherwise press
Continue.

Choose an image or pixel condition in the group's Properties.
Put the actions for a successful condition inside the main branch.
Put the alternative steps under **Else**. Only the selected branch runs.
""", "conditional branch if then otherwise else"),

    T("action-until_start", "Action reference", "Repeat until", """
Runs the actions inside the group, **then checks** an image or pixel
condition. It repeats until the condition is met or its configured
maximum number of cycles is reached.

**Example:** click Refresh, then check whether the status indicator
has changed; repeat a limited number of times.

Use a reasonable maximum to avoid an endlessly repeating workflow.
Unlike Wait until, Repeat until executes child actions each cycle.
""", "until loop condition repeated action maximum"),

    T("action-watch_start", "Action reference", "Watch region changes", """
Monitors a selected rectangle for meaningful visual changes and runs its
child actions when a new change is accepted.

**Example:** when a dashboard tile changes, play the next workflow steps.

Choose the region, Poll interval, Changed pixels %, tolerance and
confirmation count. Set **Maximum changes** or use 0 to keep watching
until Stop. Use **Test monitoring…** to preview changes without triggering
the workflow's child actions.
""", "watch screen changes monitor baseline trigger region"),

    T("trouble-no-input", "Troubleshooting", "My click or typing goes to the wrong window", """
Check these things:

1. Is the right application **visible and in front**?
2. Did you set a **Target window**, and is **Activate before input** on
   if MacroRunner needs to bring that window to the front?
3. Are X/Y coordinates correct for **Screen (absolute)** or the selected
   **Client-relative** target mode?
4. Is **Minimize when running** appropriate so MacroRunner does not cover
   the destination?
5. If using a mouse click, try **Test position** first.

MacroRunner does not bypass other windows to click inside a hidden
background application. On Wayland, desktop automation permissions may
prevent reliable input or captures.
""", "wrong window focus clicking typing not working target"),

    T("trouble-image", "Troubleshooting", "Image or text detection cannot find something", """
The image or words must be **visible on screen**. Check that nothing
covers the target and that the screen scaling, font, colors, and screenshot
are similar to those used when the workflow was created.

For **Click image**, try a smaller, distinctive reference image and
**Preview click point…**. Adjust the Confidence or restrict the search
region. For **Find text** or **Wait for text**, check local Tesseract,
the language pack, and **Live OCR preview…**.

Don't lower confidence so much that the workflow can click a different
button by mistake.
""", "not found image OCR screenshot match failed visibility"),

    T("trouble-stop", "Troubleshooting", "How do I stop a running macro?", """
In MacroRunner, click **Stop** or press **Esc**.
If global shortcuts are supported on your desktop, try
**Ctrl+Alt+Shift+F8** while another app is active.

A Stop request may wait briefly for a running operation to finish.
Actions already carried out in another application are **not undone**.
Test a short, harmless workflow before using unattended automation.
""", "emergency stuck exit cancel stop"),

    T("trouble-wont-run", "Troubleshooting", "Why won't my workflow start?", """
Check the **preflight message**. MacroRunner may refuse to run if an
action is invalid or a required file/image is missing.

Also check that you have at least one **enabled** executable action,
that your reference image exists, and that a selected target window is
available. If using OCR, install Tesseract and the appropriate language
pack first. A workflow cannot start in the middle of a control group
using Run from selected.

Some warnings require your confirmation; serious errors block the run.
""", "cannot run preflight errors blocked invalid action"),

    T("trouble-desktop", "Troubleshooting", "Windows, Ubuntu X11, Wayland and multiple monitors", """
Desktop automation uses capabilities provided by your operating system.
Windows and Ubuntu **X11/Xorg** generally support the full set of desktop
input/window features. Ubuntu **Wayland** may restrict global clicks,
keyboard hooks, window inspection, or screenshots.

Multiple monitors, negative screen coordinates and differing DPI scaling
can affect screenshot regions and click positions. Confirm actions on the
actual computer and display setup where they will run.

An installed Windows or Ubuntu build may need OS-specific permissions.
When in doubt, test with **Test position** or a read-only screen preview.
""", "linux ubuntu windows monitor screen dpi scale wayland xorg"),

    T("trouble-privacy", "Troubleshooting", "What information does MacroRunner save?", """
Workflows are stored locally as files you choose. They can contain
**typed text, clipboard text, reference image paths and variable defaults
in plain text**. Portable packages may also contain screenshot images.

Ordinary **Run History** deliberately avoids recording sensitive input
values. Error screenshots are optional and off by default. Keyboard
recording is also off until explicitly selected.

Do not include passwords in demo workflows or share a workflow file or
package without reviewing it. The local Help guide does not send your
searches or workflow to a server.
""", "security private credentials privacy sensitive log secret"),

    T("trouble-where", "Troubleshooting", "Where do I find the setting I need?", """
- To **add** a new action: search the **left Actions panel**.
- To **edit** an existing action: select it in the **middle workflow**,
  then use **Properties** on the right and click Apply changes.
- To **find** an existing action: **Edit → Find / Replace (Ctrl+F)**.
- To debug a workflow: **Breakpoint (F9)**, **Step**, **Debug gap**,
  and **History**.
- To save reusable steps: **Snippets…**.
- To set reusable values: **Variables…**.
- To change which app receives input: **Choose window…** at the bottom.
- To transfer a workflow and its images: **File → Export portable package**.
- To understand a command: **Help → User Guide (F1)**.

You can search this guide by either the technical label or an everyday
description of your problem.
""", "where locate controls buttons options search help navigation"),
)


CATEGORIES = tuple(dict.fromkeys(topic.category for topic in TOPICS))
BY_ID = {topic.id: topic for topic in TOPICS}

# Let beginners search simple questions instead of requiring exact UI labels.
QUESTION_WORDS = frozenset({
    "a", "an", "the", "and", "or", "is", "are", "of", "for", "to",
    "in", "on", "at", "with", "what", "when", "where", "why", "who",
    "how", "do", "does", "did", "can", "could", "should", "i", "my",
    "it", "this", "that", "please", "mean", "means", "don", "t",
    "doesn", "isn",
})


def search_topics(query="", category=None):
    """Return local HelpTopics. All search words must occur somewhere in a topic.

    Exact title/keyword matches appear before body-only matches. Empty searches
    preserve the curated chapter order. No user content is persisted.
    """
    if category not in (None, "All topics") and category not in CATEGORIES:
        raise ValueError("Unknown help category.")
    tokens = re.findall(r"\w+", str(query).casefold(), flags=re.UNICODE)
    words = [word for word in tokens if word not in QUESTION_WORDS]
    available = (topic for topic in TOPICS
                 if category in (None, "All topics", topic.category))
    if not words:
        return list(available)

    matches = []
    for topic in available:
        title = topic.title.casefold()
        tags = topic.keywords.casefold()
        content = f"{title} {topic.category.casefold()} {tags} {topic.body.casefold()}"
        if not all(word in content for word in words):
            continue
        score = sum(4 if word in title else 2 if word in tags else 0
                    for word in words)
        matches.append((score, topic))
    matches.sort(key=lambda pair: -pair[0])
    return [topic for _, topic in matches]
