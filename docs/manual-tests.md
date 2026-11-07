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
