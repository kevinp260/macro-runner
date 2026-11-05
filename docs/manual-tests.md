# MacroRunner 2 — Desktop QA checklist

Complete this checklist on **real desktop installations** before release.
Automated CI does not exercise native OS input hooks or screenshot capture.

## Setup

- [ ] Install/update from main with `make install` on Ubuntu Xorg/X11;
      verify app-menu entry and desktop launcher still work.
- [ ] Test from an extracted Windows build and from the Inno Setup installer.
- [ ] Open on a display around 1280×720 and resize to the minimum allowed
      dimensions; all controls must remain reachable.
- [ ] Resize each splitter pane, close/reopen, and confirm geometry is restored.
- [ ] Switch light/dark mode and restart, checking theme persistence.

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
