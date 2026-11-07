# Changelog

Notable MacroRunner changes are recorded here. Versions follow
[Semantic Versioning](https://semver.org/): MAJOR.MINOR.PATCH.

## [Unreleased]

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
