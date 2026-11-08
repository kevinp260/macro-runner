# MacroRunner 2 — Desktop QA checklist

Complete this checklist on **real desktop installations** before release.
Automated CI does not exercise native OS input hooks or screenshot capture.
A consolidated deferred test checklist for all planned PRs lives in
[GitHub Issue #64](https://github.com/kevinp260/macro-runner/issues/64).


## Setup

- [ ] Install/update from main with `make install` on Ubuntu Xorg/X11;
      verify app-menu entry and desktop launcher still work.
- [ ] Test from an extracted Windows build and from the Inno Setup installer.
- [ ] Open on a display around 1280×720 and resize to the minimum allowed
      dimensions; all controls must remain reachable.
- [ ] Resize each splitter pane, close/reopen, and confirm geometry is restored.
- [ ] Switch light/dark mode and restart, checking theme persistence.
- [ ] In View → During screen selection, test Show, Minimize, and Hide modes
      for Draw screen region, Pick start, Pick destination, and Sample pixel.
- [ ] In Hide mode, verify the desktop is unobstructed before drawing or
      picking, then MacroRunner restores automatically with captured values.
- [ ] In Minimize mode, verify MacroRunner goes to the taskbar/dock during
      selection and restores afterward; Show mode should leave it visible.
- [ ] Press Escape to cancel region drawing and confirm the window restores
      without changing the region. Check restoration after a failed pixel
      capture and when starting with the window maximized.
- [ ] Restart and confirm the screen-selection visibility choice persists,
      independently of Minimize when running.

## Structured workflow editing

- [ ] Add every action type by double-clicking the palette.
- [ ] Drag actions from palette into empty workflow, above/below an action,
      and into compatible groups; confirm expected insertion.
- [ ] Add Click Image and choose a cropped PNG from the picker.
- [ ] Add Repeat, If/Else and Repeat Until groups, then collapse and expand.
- [ ] Drag an entire Repeat group above another action; nested actions must
      remain intact and playback order must change accordingly.
- [ ] Drag an action between valid group branches; validate the new structure.
- [ ] Attempt to leave a Repeat/If empty, move an Else outside its If,
      or nest a fixed Repeat inside another Repeat; the move must revert.
- [ ] Multi-select groups and actions using Ctrl/Shift-click. Duplicate and
      Delete both plain and grouped selections.
- [ ] Undo and Redo edits and drag/drop operations.
- [ ] Scroll a long properties form, edit an image/pixel condition, apply,
      and verify the updated action is retained.
- [ ] Search in palette, clear filter, verify all action types return.
- [ ] Save a mixed workflow, reopen, and confirm repeat counts, names,
      image paths, conditions and grouped order.
- [ ] Open macros saved before version 2; verify version-2 JSON compatibility.

## Live screen-region diagnostics (Issue #35)

- [ ] Select a Watch Region Changes block, edit its region/threshold fields
      **without clicking Apply changes**, then choose **Test monitoring…**.
      Verify the live tester uses the form values but the saved macro does not change.
- [ ] On Ubuntu X11 and Windows, confirm baseline/latest/mask previews update,
      changed percentage matches obvious changes, and the confirmation counter
      reaches the configured threshold only after stable captures.
- [ ] Test A→B→A, a blinking cursor (below/above sensitivity), and a large
      watched region containing a small changing target.
- [ ] Recapture baseline, then confirm no immediate trigger until a new
      meaningful change occurs. Stop testing, restart, and close while active.
- [ ] Turn on **Minimize when running** and verify MacroRunner minimizes
      during the test and restores on close; make sure the independent preview
      does not overlap the watched area.
- [ ] Simulate screenshot permission/display failures and confirm a clear
      diagnostic message; verify the app remains responsive and no inputs fire.
- [ ] Verify Wayland limitation messaging and state test results separately
      from Windows/X11. Confirm both dark and light themes and small screens.

## Typed workflow variables and action results (Issue #58)

- [ ] Windows and Ubuntu: use toolbar Variables… editor; add and rename
      Text, Number, Boolean and Coordinates variables. Verify typed value
      parsing, blank/unset behavior, duplicate names, invalid names and
      error messages. Use Unicode and multi-line text safely.
- [ ] Bind compatible variables to Click/Move/Drag points, Wait seconds,
      Scroll amount, keyboard text, clipboard text and restore, local
      file paths, overwrite, image source and offsets, and application path.
      Type-incompatible dropdown options must be absent or rejected.
- [ ] Use Click Image's **Save result in** to capture matched-center
      coordinates, then Click/Move using that variable. Verify offsets
      do not change the reported center, and missing/moved matches do
      not leave a misleading result.
- [ ] Use Read clipboard to variable and reuse it for a subsequent paste
      or typing action. Test empty clipboard, non-text data, Unicode
      characters, Stop and Skip; ensure clipboard values are absent from
      Run History metadata and error notifications.
- [ ] Use default values, temporary run overrides, and an unset variable
      with and without an earlier producer. Check preflight warnings,
      missing/type-invalid values, and Run from Selected starting after
      the producer; never execute unexpected input on missing values.
- [ ] Repeat whole workflows and nested Repeat/If blocks. Check values
      persist within one iteration and reset from default/override on
      the next whole-workflow repeat. Test Pause, Stop and Step.
- [ ] Save/open older version-2 JSON and legacy list files; save a new
      document with definitions and field references. Verify Undo/Redo
      restores variable definitions with action edits and recovery retains
      unsaved definitions without persisting ephemeral overrides.
- [ ] Test installed Windows and Ubuntu packages. No arbitrary Python,
      shell or expression evaluation should be introduced. Ensure secret
      defaults are saved only where explicitly documented.

## Safe file and folder actions (Issue #52)

- [ ] On Windows 11 and Ubuntu, add File Exists, Wait for File, Copy File,
      Move File and Create Folder; browse local source/destination and
      type folder names manually. Verify absolute paths with Unicode and
      spaces and no command-shell interpolation.
- [ ] File Exists succeeds for a regular file and fails for missing files.
      Wait for File accepts a not-yet-present path, times out, notices newly
      created files, and honors Pause/Stop/Step and zero-second one-shot.
- [ ] Copy a text or binary file; verify byte-for-byte integrity and source
      preservation. Existing destinations must fail with Overwrite unchecked
      and replace only when explicitly checked.
- [ ] Move a file into an existing destination folder; verify the source
      is removed only when transfer completes. Existing destination conflicts
      never silently overwrite; test explicit overwrite separately.
- [ ] Stop in the middle of a large copy/move: no corrupted pre-existing
      destination or unwanted source deletion; temporary/partial files
      cleaned after cancellation and permission errors. Test low disk space
      and unavailable/removable/network drives if possible.
- [ ] Create nested directories, create the same folder twice and try a
      regular file at the target path. All failures should be actionable.
- [ ] Invalid relative paths, `..` traversal, missing destination
      directories, source/destination same inode, symlinks, directory-as-file
      misuse and permission-denied cases must fail without modifying
      unrelated files. Confirm no general delete action exists.
- [ ] Verify default Stop versus Skip failure policy, disabled actions,
      nested Repeat/If/Else, Run from Selected and that file-only workflows
      do not require PyAutoGUI, Windows focus or X11.
- [ ] Save/reload/recover new action settings, preserve old macro JSON,
      inspect Run History for no file contents, and test packaged Windows
      and Ubuntu builds.

## Image-relative click offset (Issue #49)

- [ ] On Windows 11 and Ubuntu X11, use a small cropped landmark image
      with adjacent controls. With zero X/Y offsets verify the legacy center
      click; try positive and negative X/Y offsets and both mouse buttons.
- [ ] Confirm Click Image's confidence, search region, timeout and retry
      still work; ensure detected centers already include region origin
      and offsets are applied exactly once.
- [ ] Open **Preview click point…** with unsaved offset settings: check
      reported center, signed offsets, final physical point and similarity.
      Confirm preview does not click, alter the saved action, or activate
      the target; no match and missing/corrupt image produce clear warnings.
- [ ] Offset beyond left/top or primary right/bottom edge must fail
      without a click; check exactly on screen border and just outside.
      Confirm known-obstructed and visually scaled images do not cause
      unexpected clicks.
- [ ] Bind a target window in client-relative mode: move/resize it and
      verify the offset targets the correct client point; reject offsets
      beyond its client rectangle, and abort if the target moves/focus
      changes between match and click.
- [ ] Test high DPI, display scaling, Windows secondary display,
      negative monitor origins and Ubuntu X11 multi-monitor layouts.
      Record unsupported screenshot/mouse coordinate behavior explicitly;
      do not infer support from CI.
- [ ] Pause/Resume/Step/Stop during matching and immediately before click,
      including disabled actions, skip/retry policies, and nested flows.
      Verify no click occurs after Stop or on a missing/no-match image.
- [ ] Save/reopen old macros lacking offsets, new signed-offset documents,
      Undo/Redo and local crash recovery. Test installed Ubuntu .deb and
      Windows installer, Wayland preflight limitation and no dependency
      changes.

## Wait for window state (Issue #48)

- [ ] Windows 11 and Ubuntu X11/Xorg: choose an existing window in the inspector.
      Verify title, class, handle/PID survive Apply/Save/Open/recovery; editing
      title/class clears a previously selected handle and PID.
- [ ] Wait for a delayed application launch, then detect Appears and Active
      with focus changing between windows. Duplicate title matches must fail.
      Check unique title/class matching after an app restart or title change.
- [ ] Reuse main workflow target for waits; ensure status checks never
      activate or raise the selected window.
- [ ] Minimize/unmap a window and check Hidden versus Closed. Missing
      windows are not Hidden; hidden/unmapped windows still enumerated
      by the WM must not be treated as Closed. Record X11 WM limitations.
- [ ] Test Open application → Wait for workflow target to appear →
      client-relative click; preflight must allow waiting for a missing
      window but never allow input before its existence is confirmed.
- [ ] Test timeout, zero-timeout single-check, polling interval, Skip on
      timeout, Stop during a wait and Pause/Step/Resume without UI freezes.
- [ ] Test nested Repeat, If/Else, Run from Selected, disabled actions,
      keyboard cleanup and closed/renamed windows after selection.
- [ ] Wayland must block with unsupported-backend error, not silently
      use an XWayland fallback. Test packaged Windows and Ubuntu builds,
      multi-monitor layouts and virtual workspaces.

## Open application, file, or HTTP(S) URL (Issue #47)

- [ ] Add the action, browse to a valid installed executable, and enter
      literal arguments one per line. On Windows and Ubuntu X11, test
      executable paths and argument strings with spaces, quotes and Unicode.
      Confirm no shell interpolation and no terminal is necessary.
- [ ] Change to File mode and open a local text document through the default
      app. Test file association failure, permission denial, missing files,
      and a file path in a Unicode/space-containing directory.
- [ ] Change to URL mode and open a valid HTTP and HTTPS URL with the default
      browser. Check that file://, javascript:, missing host, malformed
      ports, whitespace and userinfo URLs are refused before dispatch.
- [ ] Test launch uses unsaved inspector values without changing the saved
      workflow, and the application visibly starts only after explicit Test
      launch or regular playback. Confirm successful Test launch status.
- [ ] Use Run, Run from Selected, Step, Pause, disabled action, Stop and
      On failure: Skip/Stop. Stop before launch must avoid side effects;
      processes already launched are not killed by Stop.
- [ ] Verify a saved target-window binding does not activate before a Launch
      action, and existing absolute-coordinate, image and clipboard actions
      remain unchanged.
- [ ] Save/open and crash-recover a workflow with a launch action; verify
      old JSON remains readable and explicit arguments persist without
      silent shell parsing.
- [ ] Test Ubuntu X11 and Windows packaged installers. Check Wayland URL/file
      open behavior and default handler availability; launch success is not
      proof that a browser/app is ready for subsequent input.

## Clipboard and Unicode paste (Issue #46)

- [ ] On Windows 11 and Ubuntu X11, add Set clipboard text and Paste
      clipboard/text actions; enter harmless Unicode test content (e.g.
      Greek, Arabic, CJK and emoji) and multiline text. Verify clipboard
      transfers and Ctrl+V into a common native text editor and browser form.
- [ ] Paste the existing clipboard (blank action text). Confirm empty or
      non-text clipboard produces a clear error without pressing Ctrl+V.
- [ ] With temporary paste text and Restore enabled, confirm prior plain text
      or empty clipboard is restored; with Restore disabled, pasted text remains.
      Non-text clipboard formats must be protected unless Restore is off.
- [ ] During paste, change clipboard from a second application; MacroRunner
      must not overwrite changed data during the restore step. Verify target
      application actually consumed pasted data before restoration.
- [ ] Test slow text editors, multiline/emoji clipboard ownership and clipboard
      failure/unavailable scenarios. Confirm Stop/Pause/Step and a disabled
      action do not leak input or leave keys held.
- [ ] With target-window activation enabled/disabled, test paste when another
      window is foreground; verify no unintended clipboard text goes to the
      wrong application.
- [ ] Verify action labels, Run History and redacted export never show typed
      clipboard contents; note that workflow JSON and local crash recovery
      contain the literal plaintext. Save/open legacy and v2 workflows.
- [ ] Check packaged Windows and Ubuntu installers, plus Wayland capability
      differences (clipboard may work even if global paste hotkeys do not).

## Target-window automation (Issue #45)

- [ ] On Windows 11 and Ubuntu X11/Xorg, open **Choose window…**; confirm
      visible window title, class, PID where available, client dimensions
      and client screen origin. Confirm editor window is excluded.
- [ ] Select a target and leave **Client-relative coordinates** and
      **Activate before input** checked. Use Pick start/destination and
      Draw screen region within the target; verify client offsets, including
      a pixel sample, and save/reopen the workflow with target binding.
- [ ] Move the target window while the workflow is idle and between
      individual click/drag/move actions; verify relative positions still
      land in the correct client coordinates. Resize and test out-of-bounds
      actions; they must block before any input.
- [ ] Cover the target with another ordinary window: with activation enabled,
      verify MacroRunner brings it foreground before click/typing/scroll;
      with activation disabled, verify it refuses to send unintended input.
      Confirm no claim of true background input on minimized/covered windows.
- [ ] Close/reopen the target application (new window ID or PID), then run.
      Verify unique title/class re-identification. With two matching windows
      open, preflight must report ambiguity and block execution.
- [ ] Test Click Image/search region, If/Wait Until pixel and Watch Region
      Change with client-relative coordinates; check moved window handling,
      same-frame focus, and no wrong-window clicks.
- [ ] Put the target on secondary monitors, including negative virtual
      desktop origins and mixed display scaling. Verify real pixel alignment;
      screenshot regions with unsupported negative origins fail explicitly.
- [ ] Test global Stop, Pause/Step, action Skip policy, target loss during
      playback, Run from Selected, and held-key cleanup; no input should
      reach an unrelated window.
- [ ] On Wayland verify the picker and bound macro fail with clear
      unsupported-backend messaging, not silent fallback to XWayland.
- [ ] Open and run an older version-2 or legacy JSON without a target;
      screen-absolute behavior must remain unchanged. Verify crash recovery
      retains window identity and activation/relative options.

## Unsaved changes and crash recovery (Issue #40)

- [ ] Change actions, enabled flags, undo/redo, whole-workflow repeats and
      start delay. Confirm the unsaved title indicator appears/disappears
      correctly and Save clears it.
- [ ] With pending edits, try New, Open and Close; verify Save, Discard and
      Cancel behaviors, including cancellation of Save As and Open pickers.
- [ ] Save a file, edit it, then open a corrupt/unsupported or inaccessible
      macro file. Confirm the current edits, title and recovery remain intact.
- [ ] Make edits, allow the recovery snapshot to appear in the application-data
      folder, simulate a crash, restart and choose Restore. Verify full nested
      action settings/Unicode, repeat count and start delay are restored as
      an **unsaved copy**; original user file is untouched until explicitly saved.
- [ ] On restart choose Discard recovery and verify snapshot deletion without
      changing the last saved user file. Verify canceled Close retains edits.
- [ ] Corrupt the recovery JSON, restart, and choose Cancel: the damaged file
      must remain untouched even after a clean Close or subsequent edits.
      Explicit Discard should delete it and allow autosaving again.
- [ ] Test unwriteable recovery directory and failed normal Save: warning,
      current edits retained, and an existing file not truncated.
- [ ] Perform multiple edits quickly and confirm only one recovery snapshot
      remains, no temporary files leak, and successful Save removes it.
- [ ] On both Windows and Ubuntu/X11 check dialogs, file timestamps, privacy
      of typed text/image paths in local snapshots, and legacy JSON import.

## Breakpoints and slow-motion debugging (Issue #39)

- [ ] Set/clear a breakpoint with F9 or the toolbar on nested executable
      actions; verify the visual dot, action checkbox, and properties remain
      intact. Control-group headers should not accept breakpoints.
- [ ] Run with a breakpoint at the first and a later action. Verify no
      click/keypress occurs before the breakpoint, Resume continues exactly
      once, and Step executes one action without skipping subsequent breaks.
- [ ] Put a breakpoint inside Repeat and If/Else; confirm it triggers for
      each reached iteration/branch and not on a skipped branch.
- [ ] Mark a disabled action, confirm it never pauses, enable it again and
      confirm the breakpoint then triggers.
- [ ] Run from Selected after an earlier marked action; earlier breakpoints
      must be skipped and later ones still reached.
- [ ] Use Stop / emergency Stop while paused at a breakpoint; no subsequent
      action should run and held keys must be released.
- [ ] Try Debug gap 0, 0.5 and 2 seconds; verify a delay between actions,
      cancellation during the gap, and Pause/Resume/Step interaction.
- [ ] Save/reopen a workflow, Undo/Redo and rearrange/duplicate marked
      actions; confirm breakpoints are editor-only and not in saved JSON.
- [ ] With Minimize when running enabled, confirm the editor returns for
      breakpoint controls then minimizes again on Resume/Step. Test both
      Windows and Ubuntu/X11, including theme and focus behavior.

## Pre-run validation (Issue #38)

- [ ] Run, Run from Selected, and Step first validate the applied workflow;
      no screenshot, click, typing, or recording should occur during checks.
- [ ] Configure a missing or corrupt reference image and an image larger than
      its chosen search region. Confirm blocking findings and clear fixes.
- [ ] Use a valid image reference; confirm the validator does not flag it.
      Test legacy JSON workflows and newly created nested blocks.
- [ ] Check warnings for off-primary-screen click/drag/pixel coordinates and
      out-of-bounds watch/image regions; verify another monitor may justify
      choosing **Run anyway**.
- [ ] Verify a restricted Wayland session shows the capability warning,
      without claiming background input or screenshot access is supported.
- [ ] Select findings inside nested Repeat/If branches and **Go to action**;
      confirm the relevant tree action is selected and inspector opens.
- [ ] Confirm **Run anyway** is offered only for warnings, not errors.
      Cancel must not start playback or change run history.
- [ ] Confirm disabled image actions and images before Run from Selected do
      not trigger false blocking errors. Normal valid workflows run directly.
- [ ] Check both themes, keyboard navigation, smaller screens and packaged
      Ubuntu X11/Windows builds; document actual environment and results.

## Per-action failure handling (Issue #37)

- [ ] Select a Wait Until or Click Image action: switch On failure between
      Stop / Skip / Retry, edit retry count and delay, and confirm the values
      persist after Save/Open and undo/redo.
- [ ] Confirm Click, Move, Drag, Type, Hold/Release and other input actions
      expose Stop and Skip, **not** automatic Retry (to avoid duplicate input).
- [ ] Simulate a missing image or pixel condition: retry a finite number of
      times, then succeed or fail after the configured per-attempt timeout.
      Inspect Run History for attempt numbers and sanitized errors.
- [ ] Set Skip for a missing visual condition inside a nested Repeat and If;
      confirm the next executable step runs and skips are counted separately.
- [ ] While waiting for a retry delay, test Stop, Pause/Resume and Step; verify
      no retry continues after Stop and emergency mouse-corner fail-safe
      errors are never suppressed.
- [ ] Cause a click or keyboard action to fail under Skip. Verify the action
      is never blindly replayed, and document that partial side effects may
      still have occurred.
- [ ] Load an older JSON macro without failure-policy fields; confirm the
      default remains Stop. Verify bad policy names/counts reject on import.

## Run history and diagnostic logs (Issue #36)

- [ ] On real Ubuntu/X11 and Windows installations, run a successful workflow,
      stop one during playback, and trigger an error. Verify separate run
      records and accurate outcomes, timestamps and durations.
- [ ] Run nested If/Else and Watch Region Changes; verify structural action
      paths, condition changes, image-match results, and watcher-trigger logs.
- [ ] Test Pause, Resume and Step; inspect their timeline entries and timing.
- [ ] Confirm typed text, keyboard shortcuts, clipboard values, user-defined
      action names, image paths, and raw error strings are absent from history
      files and redacted JSON exports.
- [ ] Confirm no failure screenshot is saved by default; opt in explicitly,
      trigger an error, inspect the local screenshot, cap retention, disable
      capture, and clear all saved images/history.
- [ ] Open History while a macro runs and after a restart; copy selected
      diagnostics, export JSON, reject clear, then confirm clear works.
- [ ] Confirm slow/large or corrupt history files do not block automation;
      check desktop permissions and no unbounded growth.

## Playback and visual automation

- [ ] Run / Pause / Resume / Stop / Step, including while a Wait is active.
- [ ] Run from Selected both outside groups and from a valid block start.
- [ ] Confirm run progress highlights the currently executing action,
      scrolls into view and updates status correctly.
- [ ] With real screenshots, test Click Image, Wait Until,
      image disappearance, pixel match and tolerance.
- [ ] Confirm failed image detection times out and reports an error.
- [ ] Run both branches of If/Else and a Repeat Until cycle limit.
- [ ] Test Press, Type, Hold, Release, Scroll and Drag using harmless apps.
- [ ] Stop after Hold but before Release; key must be released by cleanup.
- [ ] Confirm global pause/stop on an X11/Windows desktop.

## Recording

- [ ] Record mouse clicks (no keyboard capture); edit, save and replay.
- [ ] Record mixed keyboard+mouse events after opt-in confirmation.
- [ ] Verify keyboard recording defaults to disabled and warns about secrets.
- [ ] Verify input within MacroRunner's own window isn't captured.
- [ ] Stop during countdown; no listeners should be left running.
- [ ] Stop normal recording; ensure no input afterward is recorded.
- [ ] Undo the recorded session, redo, then save and reload.

## Release sign-off

Record the OS version, desktop session (Xorg/Wayland), resolution, and
pass/fail notes for any failures. Do not use production credentials or
sensitive applications during keyboard recording.
