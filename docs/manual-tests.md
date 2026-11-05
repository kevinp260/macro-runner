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

## Result reporting

Mark each check `[x]` when it passes. For any failure, record OS/version, Xorg vs Wayland, the action settings, expected behavior, actual behavior, and reproduction steps.
