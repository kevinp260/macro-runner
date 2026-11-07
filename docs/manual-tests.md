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
