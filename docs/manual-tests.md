# MacroRunner — manual QA checklist (PRs 1–3)

Run all checks on a non-sensitive target application (a blank text document, simple browser page, or drawing canvas). Back up existing JSON macros first.
Run through the functional checks on Windows, then repeat key input checks on Ubuntu **Xorg/X11**. Wayland input automation is not supported reliably.

## Preparation / installation

- [ ] **I1 — Windows development build:** With Python 3.12 installed, create `.venv`, install packages, run unit tests, and build `dist/MacroRunner.exe` using `MacroRunner.spec`. It launches without a console error.
- [ ] **I2 — Windows installer:** Compile `installer.iss` using Inno Setup, install the generated setup executable, and verify desktop and Start Menu shortcuts.
- [ ] **I3 — Windows application lifecycle:** Close and reopen the installed app, try launching a second instance (the first remains), and check the uninstall entry.
- [ ] **I4 — Ubuntu pipx install:** In an Xorg session, run `make install`, launch `macro-runner` and open it from the application menu.
- [ ] **I5 — Ubuntu development:** Run `make setup`, `make test`, `make run`; optionally `make build` and launch `dist/MacroRunner`.
- [ ] **I6 — Ubuntu launcher:** Close and reopen, check launcher icon/visibility and user-level uninstall (`make uninstall`) only after functional tests.

## Actions and editing

- [ ] **A1 — Click:** Add a click on a harmless target; verify the button, coordinates, click count and interval.
- [ ] **A2 — Wait:** Add a 3-second wait between observable actions; verify it delays the following action.
- [ ] **A3 — Key/Type:** Type a short test string and press a simple key/combo in a scratch text editor.
- [ ] **A4 — Move:** Move to chosen X/Y coordinates and try the Click tab's `Test Move` without clicking.
- [ ] **A5 — Scroll:** Scroll up and down using positive/negative step counts; verify direction and amount.
- [ ] **A6 — Drag:** Drag across a drawing canvas or selection area, checking start/end positions, mouse button and duration.
- [ ] **A7 — Full editor:** Double-click Click, Wait, Key, Move, Scroll and Drag actions; edit their relevant fields and save. Change one action type and verify it runs as the new type.
- [ ] **A8 — Edit validation:** Enter a negative duration, zero repeats, invalid coordinates or invalid action-specific value; Save rejects it and keeps the previous action.
- [ ] **A9 — Cancel editing:** Change fields then Cancel; the original action remains untouched.
- [ ] **A10 — Reorder and duplicate:** Move Up/Down, Duplicate, Rename and Edit Repeat; verify the list order and execution match.
- [ ] **A11 — Delete and clear:** Delete one action and use Clear; verify the confirmation dialog avoids accidental full deletion.
- [ ] **A12 — Enabled state:** Disable an action, verify `[OFF]`, run and confirm it is skipped; re-enable it and check it runs.
- [ ] **A13 — Loop semantics:** Set per-action repeat = 2 and whole-sequence repeat = 3; verify exactly six executions for that action.
- [ ] **A14 — Subloop execution:** Add A, B, Loop Start (5 cycles), C, D, Loop End, E; verify A/B once, C/D five times, and E once.
- [ ] **A15 — Repeat inside subloop:** Make C repeat twice; verify C/C/D for each inner cycle. Then repeat the whole sequence twice and verify totals.
- [ ] **A16 — Loop editing:** Insert Start before a selected action, End after another, move markers, rename Loop Start, edit its cycle count, save/reload.
- [ ] **A17 — Invalid loops:** Verify Save/Run rejects incomplete, empty or nested blocks, but normal actions can be edited to correct the macro.
- [ ] **A18 — Stop/pause inside subloop:** Pause during a Wait inside the block and resume; Stop during a later cycle and verify no further actions execute.

## Playback and safety

- [ ] **P1 — Start delay:** Start with a 3-second delay; verify progress and no input automation before the countdown finishes.
- [ ] **P2 — Progress:** Run several enabled and disabled actions over multiple loops; verify loop count, step counter and active list selection.
- [ ] **P3 — Pause/resume in Wait:** Pause during a long Wait and resume; the remaining wait is preserved and later actions do not execute while paused.
- [ ] **P4 — Pause countdown:** Pause during start delay, resume and verify remaining countdown continues.
- [ ] **P5 — Stop while paused:** Stop a paused macro; it exits without executing further actions and controls reset.
- [ ] **P6 — Stop long/repeated run:** Stop during a long Wait and between repeated Click/Key actions; playback stops promptly at a safe point.
- [ ] **P7 — Emergency fail-safe:** During playback move the pointer to the top-left corner; PyAutoGUI stops input execution.
- [ ] **P8 — Lock edits/recording:** Try to edit, reorder, delete or record during playback; actions should not change, and a second run should not start.
- [ ] **P9 — Completion/abort:** Verify Run/Pause/Stop buttons reset after successful completion, Stop and a PyAutoGUI failure; the app remains usable.
- [ ] **P10 — Native drag limitation:** During a long Drag, expect pause/stop to take effect after the ongoing native drag completes; verify the macro does not continue afterward.
- [ ] **P11 — Global Pause/Stop:** Focus another application; verify Ctrl+Alt+Shift+F6 pauses/resumes, and Ctrl+Alt+Shift+F8 stops the macro.
- [ ] **P12 — Global shortcuts unavailable:** On a restricted desktop session, the app must still launch and local Pause/Stop continue to work.
- [ ] **P13 — Step from idle:** Click Step; verify exactly one action executes, and repeat presses advance one action at a time, including through repeat blocks.
- [ ] **P14 — Pause then Step:** Pause a running macro, press Step and verify one full action executes; Resume returns to continuous execution.
- [ ] **P15 — Step and Stop:** Stop while waiting for the next Step; confirm the worker exits and buttons reset.
- [ ] **P16 — Run from Selected:** Select a middle action and use Run from Selected; verify preceding actions are skipped, the remainder executes once, and start delay applies.
- [ ] **P17 — Start inside repeat block:** Select an action inside a repeat block; verify execution starts there in the first cycle, completes later cycles normally, and respects total step counts.
- [ ] **P18 — Selected Loop End:** Run from a Loop End marker; verify playback skips that block and proceeds to the next action, or reports no executable actions when none remain.

**Shortcut scope:** F5/F6/Esc remain Tkinter window shortcuts. Global Ctrl+Alt+Shift+F6 (Pause/Resume) and Ctrl+Alt+Shift+F8 (Stop) use pynput and require OS-level permissions; verify in Windows and Ubuntu Xorg. PyAutoGUI's top-left fail-safe remains available.

## Recording and persistence

- [ ] **R1 — Record clicks:** Start mouse recording, click a harmless external target several times, stop, inspect and replay actions.
- [ ] **R2 — Record waits:** Enable automatic waits and verify gaps of at least the configured threshold create Wait actions.
- [ ] **R3 — Recording repeats:** Set recorded repeats >1 and verify captured clicks use that count.
- [ ] **R4 — Cancel countdown:** Cancel recording during the 3-second countdown; verify no mouse listener starts.
- [ ] **R5 — Ignore MacroRunner UI:** Click the app's own buttons while recording; no unintended recorded actions are added.
- [ ] **R6 — Save new format:** Save with a custom global loop count, start delay, disabled action and Scroll/Drag; reload and check everything is restored.
- [ ] **R7 — Load legacy JSON:** Load a JSON array saved by the original app; verify actions load, default enabled state, and that existing global settings stay unchanged.
- [ ] **R8 — Invalid file:** Try malformed/invalid JSON; verify an error appears and the current valid macro is not lost.
- [ ] **R9 — Reopen and reuse:** Close/reopen the app, load a saved macro, execute it and verify the results.

## Visual matching and conditional logic

- [ ] **V1 — Image match:** Save a cropped image from a harmless desktop app, load it in Vision, configure 0.9 confidence and verify Click Image clicks the correct point.
- [ ] **V2 — Missing image:** Hide the matching item, set a 2-second timeout, and verify Click Image aborts with a clear error without clicking.
- [ ] **V3 — Image region:** Use a bounded search region and verify matching happens only inside it; check coordinates remain screen-relative.
- [ ] **V4 — Wait for appearance:** Configure Wait Until (image matches), then make the target appear during polling.
- [ ] **V5 — Wait for disappearance:** Use image not_matches and verify it waits until the item is hidden.
- [ ] **V6 — Pixel matching:** Use a colored status indicator, configure its coordinates, hex RGB color and tolerance, then change the color to trigger the condition.
- [ ] **V7 — If/Else:** Check both true and false branches, as well as an If without Else.
- [ ] **V8 — Repeat Until:** Make a condition become true after several cycles and verify the block exits early and continues after End Until.
- [ ] **V9 — Cycle limit:** Keep the condition false and verify Repeat Until aborts at the configured maximum cycles.
- [ ] **V10 — Nested conditional and fixed loops:** Put If or Repeat Until inside a fixed Repeat Block, verify execution order, Pause and Stop.
- [ ] **V11 — Validation:** Verify Save/Run rejects an incomplete or empty If/Until block, invalid pixel color, missing image and invalid confidence.
- [ ] **V12 — Persistence:** Save/reload a vision macro including image path, region, pixel settings, thresholds and markers; verify values remain.
- [ ] **V13 — Start selection:** Verify Run from Selected refuses to begin in the middle of an If/Until block, and accepts its opening marker.
- [ ] **V14 — Cross-platform:** Repeat a basic image and pixel test on Windows and Ubuntu Xorg; confirm failure messages for screenshot permission restrictions.

## Keyboard actions, recording, and multi-selection (PR #11)

- [ ] **K1 — Hold/Release:** Add Hold Shift, click a selectable item, Release Shift; confirm behavior matches manually holding Shift.
- [ ] **K2 — Stop cleanup:** Begin a Hold modifier, interrupt execution before Release, and verify the modifier does not remain stuck.
- [ ] **K3 — Error cleanup:** Trigger an error after a Hold and confirm the modifier is released.
- [ ] **K4 — Invalid release:** Run Release for a key not held by the macro; verify playback aborts clearly without releasing another key.
- [ ] **K5 — Repeated keydown:** Recording repeated keydown events (autorepeat) does not create repeated Hold actions.
- [ ] **K6 — Opt-in privacy:** Confirm keyboard capture starts disabled and requires confirmation; cancel leaves capture disabled.
- [ ] **K7 — Keyboard capture:** Record a harmless key sequence and Ctrl/Shift shortcuts in a scratch text editor; verify replayable Key/Hold/Release actions.
- [ ] **K8 — Mixed capture:** Enable keyboard recording and mouse recording together; verify correct event order and optional wait actions.
- [ ] **K9 — Stop recording:** Verify Stop Recording removes both listeners; keys typed afterward are not recorded.
- [ ] **K10 — UI exclusion:** Keyboard input directed to MacroRunner's own editor and buttons is not recorded.
- [ ] **K11 — Multi-select:** Ctrl-click and Shift-click multiple actions; move Up/Down, Duplicate and Delete while preserving relative order.
- [ ] **K12 — Marker guard:** Duplicate selection containing a control marker; verify the operation is rejected without editing the list.
- [ ] **K13 — Undo/Redo:** Add, edit, rename, duplicate, move, delete, disable and load actions, then undo and redo each change.
- [ ] **K14 — Recording history:** Record several actions, then Undo once; verify the entire recording session is reverted and Redo restores it.
- [ ] **K15 — History after edit:** Undo a change, make a new edit, verify Redo is cleared.
- [ ] **K16 — Persistence:** Save/reload a macro containing Key Hold and Release; verify the saved representation and playback.
- [ ] **K17 — Safety:** Try actions and Undo while playback/recording are active; verify the list cannot change.

## Result reporting

Mark each check `[x]` when it passes. For any failure, record OS/version, Xorg vs Wayland, the action settings, expected behavior, actual behavior, and reproduction steps.
