# Changelog

Notable MacroRunner changes are recorded here. Versions follow
[Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.

## [Unreleased]

- Added opt-in Tesseract-backed Find text and Wait for text with region/window scoping, confidence thresholds, optional guarded center click, live local preview and language-pack diagnostics (Issue #61). OCR engine remains separately installed; no remote OCR.

- Added portable workflow ZIP export/import with bundled image references, automatic managed-asset rebasing, atomic output, strict archive validation, checksum verification and review prompts (Issue #60).

- Added local named workflow snippets: structural group/selected-action snapshots, searchable previews, copy-only insertion, variable dependency merging, image validation, safe library editing, and import/export (Issue #59). Text variable defaults are intentionally excluded from snippets.

- Added typed workflow variables with validated per-field bindings, optional v2 document defaults, session-only run overrides, clipboard-read and image-center outputs, scoped repeat resets, and editor undo/recovery (Issue #58).

- Added explicit-path File Exists, Wait for File, Copy File, Move File and Create Folder actions with no-shell operations, no-overwrite defaults, atomic staged overwrite, Stop cleanup, and local file pickers (Issue #52).

- Added signed X/Y offsets to Click Image (zero preserves center clicks),
  read-only click-point preview, final-point bounds checks, and target-client
  containment before clicking (Issue #49).

- Added cancellable Wait for Window actions for appear/active/hidden/closed
  states using the existing Win32/X11 targeting identity, including a picker,
  title/class fallback, timeout and polling controls (Issue #48).

- Added an Open Application/File/URL action with shell-free explicit arguments,
  OS default file/HTTP(S) handlers, preflight path/permission checks, and a
  direct inspector file picker and test-launch control (Issue #47).

- Added Set clipboard text and Paste clipboard/text actions with Unicode,
  optional best-effort prior-text restoration, Pause/Stop support, Qt clipboard
  thread safety, and redacted workflow labels/diagnostics (Issue #46).

- Added foreground target-window selection on Windows/X11, safe re-identification,
  client-relative action coordinates, and explicit Wayland/background limitations
  (Issue #45).


- Added an unsaved-workflow title indicator, Save/Discard/Cancel prompts,
  bounded atomic local recovery snapshots, startup restore/discard, and
  atomic normal workflow saves (Issue #40).

- Added editor-only F9 breakpoints before enabled actions, step/resume
  debugging through nested flows, and a local slow-playback gap (Issue #39).

- Added pre-run workflow validation, blocking errors and acknowledged warnings,
  with direct navigation to offending workflow actions (Issue #38).

- Added per-action Stop/Skip/Retry failure handling, bounded retry counts and
  delays for pre-input visual-condition timeouts, and Run History retry/skip
  diagnostics (Issue #37).

- Added local, bounded Run History and action-level diagnostic events (Issue #36),
  with copy/redacted-export, paused/stopped/error outcomes, and opt-in failure
  screenshots with retention controls.

- Added a read-only screen-region diagnostics window to test live screenshot
  differences, confirmation rules, and A→B→A state transitions before
  executing macros (Issue #35).

## [2.1.0] — Pending release

This version is prepared but **not published** until desktop QA is complete
and a maintainer creates the matching `v2.1.0` tag.

### Added
- Native Ubuntu `.deb` and Windows Inno Setup installer builds, with automated
  packaging and startup smoke tests.
- Optional minimize-on-playback preference, remembered between sessions.
- Visual workflow action checkboxes to identify and toggle disabled commands.
- Stateful Watch Region Changes workflow block with configurable monitoring,
  thresholds, confirmations, and trigger limits.
- Drag-to-select screen rectangles, plus configurable show/minimize/hide behavior
  during screen selection and coordinate/pixel picking.
- Application version display via Help → About MacroRunner.

### Improved
- Ubuntu source installer detects missing system dependencies and asks
  permission before installing them.
- Rounded panel gutters, inspector minimum widths, label spacing, and
  cross-theme numeric/dropdown arrow styling.
- Alignment of numeric and text field contents in the inspector and playback
  controls.
- Version synchronization across Python packaging, Ubuntu, and Windows.

### Fixed
- Preserve the last confirmed screen-region screenshot between monitoring
  cycles; changes during nested action execution are no longer discarded by
  automatically resetting the baseline.
- Screen-selection window restoration after completion, cancellation, or
  capture failure.
- Platform CI tests and packaging checks, with independent Ubuntu/Windows
  test outcomes.

## [2.0.0] — PySide6 editor baseline

- Replaced the previous Tkinter interface with a three-pane PySide6 structured
  workflow editor supporting nested conditions, loops, property inspection,
  workflow drag-and-drop, and undo/redo.
- Retained support for existing version-2 workflow JSON files.

Release artifacts and published versions are available through GitHub Releases
once a version tag has been approved.
