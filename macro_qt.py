"""Modern PySide6 desktop application for MacroRunner.

Qt owns all widgets. Existing action validation, JSON, keyboard, image, and
playback logic live in independent modules and remain compatible.
"""
import json
import os
import queue
import sys
import time
from dataclasses import asdict
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer, QObject, Signal, QPoint, QStandardPaths
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QToolBar, QLabel, QPushButton, QFileDialog, QMessageBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QProgressBar, QAbstractItemView, QGridLayout
)

from macro_model import Action, parse_document, serialize_document
from macro_flow import CONTROL
from macro_editing import ActionHistory
from macro_qt_workflow import ActionPalette, WorkflowTree, KINDS
from macro_qt_properties import PropertiesPanel, pad_spinbox_text
from macro_qt_region import RegionPicker
from macro_qt_monitor import RegionMonitorDialog
from macro_diagnostics import RunHistoryStore, RunSession
from macro_qt_history import RunHistoryDialog
from macro_version import app_version
from macro_runtime import MacroExecutor
from macro_preflight import inspect_workflow
from macro_recovery import RecoveryStore, atomic_json_write
from macro_windows import (WindowBinding, WindowManager, WindowUnavailable,
                           validate_target, target_from_window)
from macro_qt_windows import WindowPickerDialog
from macro_qt_clipboard import QtClipboardClient
from macro_qt_preflight import PreflightDialog
from macro_keys import KeyboardRecorder, normalize_event_key
from macro_ui_assets import ICON_DIR
import PySide6.QtSvg  # Ensure SVG chevrons also work in PyInstaller distributions.


DARK = """
QMainWindow, QWidget { background: #15191f; color: #e6eaf0; }
/* Text should sit directly on its parent panel, not paint opaque rectangles. */
QLabel { background: transparent; border: none; padding: 1px 3px; }
QLabel#panelHeading { font-size: 16px; font-weight: 700; padding: 4px 3px 2px 3px; }
QLabel#muted, QLabel#panelHint { color: #94a1b1; }
QLabel#panelHint { padding: 2px 3px 6px 3px; }
QLabel#actionCount {
  color: #b7c9df; background: #273241; border: 1px solid #394b60;
  border-radius: 6px; padding: 3px 8px;
}
QFrame#panel { background: #1b222c; border: 1px solid #303a49; border-radius: 10px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: #222b37; color: #eaf0f7; border: 1px solid #3a4758;
  border-radius: 6px; padding: 7px; min-height: 20px;
}
QTreeWidget, QListWidget, QScrollArea {
  background: #1b222c; color: #e6eaf0; border: none;
  outline: 0; alternate-background-color: #242e3a;
}
QTreeWidget::item, QListWidget::item { padding: 8px 5px; min-height: 24px; }
QTreeWidget::item:selected, QListWidget::item:selected {
  background: #244e74; color: white; border-radius: 5px;
}
QPushButton, QToolButton {
  background: #283341; color: #e6eaf0; border: 1px solid #415064;
  border-radius: 7px; padding: 7px 12px;
}
QPushButton:hover, QToolButton:hover { background: #34465d; }
QPushButton:disabled, QToolButton:disabled { color: #718096; background: #212934; }
QPushButton#primaryButton { background: #3276b3; color: white; }
QPushButton#primaryButton:hover { background: #418ed2; }
QToolBar { background: #1b222c; border-bottom: 1px solid #303a49;
           spacing: 8px; padding: 8px; }
QSplitter::handle { background: #15191f; }
QSplitter::handle:hover { background: #34465d; }
QStatusBar { background: #1b222c; color: #b8c8d8; }
QScrollBar:vertical { background: #202834; width: 11px; }
QScrollBar::handle:vertical { background: #4a596c; border-radius: 5px; }
QCheckBox { spacing: 8px; }
"""
LIGHT = """
QMainWindow, QWidget { background: #f4f6f9; color: #263344; }
/* Transparent labels preserve the panel background and its rounded corners. */
QLabel { background: transparent; border: none; padding: 1px 3px; }
QLabel#panelHeading { font-size: 16px; font-weight: 700; padding: 4px 3px 2px 3px; }
QLabel#muted, QLabel#panelHint { color: #68788a; }
QLabel#panelHint { padding: 2px 3px 6px 3px; }
QLabel#actionCount {
  color: #536b83; background: #eaf0f7; border: 1px solid #d7e1ec;
  border-radius: 6px; padding: 3px 8px;
}
QFrame#panel { background: white; border: 1px solid #dce3ea; border-radius: 10px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: white; color: #253242; border: 1px solid #c9d3df;
  border-radius: 6px; padding: 7px; min-height: 20px;
}
QTreeWidget, QListWidget, QScrollArea {
  background: white; color: #253242; border: none; outline: 0;
}
QTreeWidget::item, QListWidget::item { padding: 8px 5px; min-height: 24px; }
QTreeWidget::item:selected, QListWidget::item:selected {
  background: #d4e9ff; color: #153e6a; border-radius: 5px;
}
QPushButton, QToolButton {
  background: #f7faff; color: #263344; border: 1px solid #c8d5e2;
  border-radius: 7px; padding: 7px 12px;
}
QPushButton:hover, QToolButton:hover { background: #e1ecf7; }
QPushButton:disabled, QToolButton:disabled { color: #9aa6b5; }
QPushButton#primaryButton { background: #2675bb; color: white; }
QToolBar { background: white; border-bottom: 1px solid #dce3ea; padding: 8px; }
QSplitter::handle { background: #f4f6f9; }
QSplitter::handle:hover { background: #dce3ea; }
QStatusBar { background: white; color: #4c5b6d; }
"""


def field_controls_style(theme):
    """Use packaged SVG arrows and a single rounded border for each field."""
    if theme not in ("dark", "light"):
        raise ValueError("Unknown theme")
    divider, button, hover = (
        ("#3a4758", "#293746", "#38506a") if theme == "dark"
        else ("#c9d3df", "#e9f1fa", "#d8e8f7")
    )
    up = (ICON_DIR / f"chevron-up-{theme}.svg").as_posix()
    down = (ICON_DIR / f"chevron-down-{theme}.svg").as_posix()
    return f"""
/* QComboBox draws its label itself, while spinboxes use an embedded
   QLineEdit. Give the combo its own inset and set the spinbox editor's
   margin in Python (QSS on the outer spinbox alone does not move its text). */
QLineEdit {{ padding-left: 10px; }}
QComboBox {{ padding: 7px 29px 7px 11px; }}
QSpinBox, QDoubleSpinBox {{ padding: 7px 29px 7px 0px; }}
QSpinBox > QLineEdit, QDoubleSpinBox > QLineEdit {{
  padding: 0; border: none; background: transparent;
}}
QComboBox::drop-down {{
  subcontrol-origin: border;
  subcontrol-position: top right;
  width: 26px;
  background: {button};
  border-left: 1px solid {divider};
  border-top-right-radius: 5px;
  border-bottom-right-radius: 5px;
}}
QComboBox::drop-down:hover {{ background: {hover}; }}
QComboBox::down-arrow {{
  image: url("{down}");
  width: 12px;
  height: 12px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
  subcontrol-origin: border;
  subcontrol-position: top right;
  width: 25px;
  background: {button};
  border-left: 1px solid {divider};
  border-top-right-radius: 5px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
  subcontrol-origin: border;
  subcontrol-position: bottom right;
  width: 25px;
  background: {button};
  border-left: 1px solid {divider};
  border-top: 1px solid {divider};
  border-bottom-right-radius: 5px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
  background: {hover};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
  image: url("{up}");
  width: 10px;
  height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
  image: url("{down}");
  width: 10px;
  height: 10px;
}}
"""


class WorkerSignals(QObject):
    progress = Signal(int, int, int, int, object)
    diagnostic = Signal(object)
    failure_capture = Signal(object)
    finished = Signal(bool, str)


class MacroWindow(QMainWindow):
    global_pause = Signal()
    global_stop = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MacroRunner — Workflow editor")
        icon_file = os.path.join(
            getattr(sys, "_MEIPASS", os.path.dirname(__file__)),
            "macro_runner_icon.ico"
        )
        if os.path.isfile(icon_file):
            self.setWindowIcon(QIcon(icon_file))
        # Enforce usable panel widths rather than letting the inspector clip.
        self.setMinimumSize(1020, 620)
        self.resize(1180, 760)
        self.settings = QSettings("MacroRunner", "Desktop")
        self.actions = []
        self.window_target = None
        self.clipboard_client = QtClipboardClient(self)
        self.history = ActionHistory(60)
        data_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation)
        if not data_dir:
            data_dir = str(Path.home() / ".macrorunner")
        self.diagnostics_store = RunHistoryStore(
            Path(data_dir) / "run-history.json",
            max_screenshots=self.settings.value(
                "diagnostics_capture_limit", 5, type=int))
        self._run_session = None
        self._pending_failure_capture = None
        self.run_history_dialog = None
        self.current_file = None
        self._recovery_source_file = None
        self.recovery_store = RecoveryStore(Path(data_dir) / "workflow-recovery.json")
        self._saved_state = None
        self._recovery_warning_shown = False
        self._recovery_locked = False
        self.executor = None
        self._restore_after_run = False
        self._debug_window_visible = False
        self.run_signals = WorkerSignals()
        self.run_signals.progress.connect(self._progress)
        self.run_signals.diagnostic.connect(self._diagnostic_event)
        self.run_signals.failure_capture.connect(self._failure_capture_received)
        self.run_signals.finished.connect(self._finished)
        self.events = queue.Queue()
        self.recording = False
        self.record_pending = False
        self.capture_keyboard = False
        self.capture_waits = True
        self.capture_min_wait = .3
        self.capture_repeats = 1
        self.capture_last = None
        self.capture_history = False
        self.capture_token = 0
        self.keyboard_recorder = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.hotkeys = None
        self.region_picker = None
        self.region_monitor = None
        self._monitor_restore_state = None
        self._close_after_monitor = False
        self._screen_selection_active = False
        self._screen_selection_restore = None
        self._build_ui()
        self._restore_settings()
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setSingleShot(True)
        self.recovery_timer.setInterval(1000)
        self.recovery_timer.timeout.connect(self._write_recovery)
        self._saved_state = deepcopy(self._document_state())
        self._refresh_unsaved()
        self.repeats.valueChanged.connect(self._after_edit)
        self.delay.valueChanged.connect(self._after_edit)
        self._start_hotkeys()
        self.global_pause.connect(self.pause_run)
        self.global_stop.connect(self.stop_run)
        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(self._drain_capture)
        self.event_timer.start(35)
        self._set_status("Ready — drag an action into the workflow.")

    def _build_ui(self):
        bar = QToolBar("Workflow", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        self.toolbar_actions = {}
        for key, label, shortcut, handler in [
            ("new", "New", "Ctrl+N", self.new_workflow),
            ("open", "Open", "Ctrl+O", self.open_workflow),
            ("save", "Save", "Ctrl+S", self.save_workflow),
            ("run", "Run", "F5", self.run_workflow),
            ("pause", "Pause", "F6", self.pause_run),
            ("stop", "Stop", "Esc", self.stop_run),
            ("step", "Step", "", self.step_run),
            ("run_from", "Run from selected", "", self.run_selected),
            ("breakpoint", "Breakpoint", "F9", self.toggle_breakpoint),
            ("history", "History", "", self.show_run_history),
            ("record", "Record", "Ctrl+R", self.record_toggle),
            ("undo", "Undo", "Ctrl+Z", self.undo),
            ("redo", "Redo", "Ctrl+Y", self.redo),
        ]:
            if key in ("run", "record", "undo"):
                bar.addSeparator()
            action = QAction(label, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(handler)
            bar.addAction(action)
            self.toolbar_actions[key] = action

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)
        self.setCentralWidget(central)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(12)  # A real gutter, not a line across rounded borders.

        palette_panel = QFrame()
        palette_panel.setObjectName("panel")
        palette_panel.setMinimumWidth(195)
        palette_layout = QVBoxLayout(palette_panel)
        heading = QLabel("Actions")
        heading.setObjectName("panelHeading")
        palette_layout.addWidget(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search actions…")
        self.search.textChanged.connect(self._filter_palette)
        palette_layout.addWidget(self.search)
        self.palette = ActionPalette()
        self.palette.itemDoubleClicked.connect(
            lambda item: self.tree.insert_kind(item.data(Qt.ItemDataRole.UserRole))
        )
        palette_layout.addWidget(self.palette, 1)
        hint = QLabel("Double-click or drag into workflow")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        palette_layout.addWidget(hint)
        self.splitter.addWidget(palette_panel)

        editor_panel = QFrame()
        editor_panel.setObjectName("panel")
        editor_panel.setMinimumWidth(410)
        editor_layout = QVBoxLayout(editor_panel)
        title_row = QHBoxLayout()
        label = QLabel("Workflow")
        label.setObjectName("panelHeading")
        title_row.addWidget(label)
        title_row.addStretch()
        self.counter = QLabel("0 actions")
        self.counter.setObjectName("actionCount")
        title_row.addWidget(self.counter)
        editor_layout.addLayout(title_row)
        self.tree = WorkflowTree()
        self.tree.actions_changed.connect(self._changed)
        self.tree.invalid_change.connect(
            lambda text: QMessageBox.warning(self, "Invalid workflow structure", text))
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        editor_layout.addWidget(self.tree, 1)

        # Two compact rows prevent toolbar labels being cropped at minimum size.
        buttons = QGridLayout()
        buttons.setSpacing(6)
        for i, (text, handler) in enumerate([
            ("Duplicate", self.duplicate), ("Delete", self.delete),
            ("Enable / Disable", self.tree.toggle_enabled_selection),
            ("Collapse all", self.tree.collapseAll),
            ("Expand all", self.tree.expandAll),
            ("Breakpoint (F9)", self.toggle_breakpoint),
        ]):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button, i // 3, i % 3)
        for column in range(3):
            buttons.setColumnStretch(column, 1)
        editor_layout.addLayout(buttons)
        self.splitter.addWidget(editor_panel)

        self.inspector = PropertiesPanel()
        self.inspector.apply_action.connect(self._apply_property)
        self.inspector.pick_coordinates.connect(self._pick_coordinates)
        self.inspector.test_move.connect(self._test_move)
        self.inspector.pick_region.connect(self._pick_region)
        self.inspector.test_monitoring.connect(self._test_monitoring)
        self.splitter.addWidget(self.inspector)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        root.addWidget(self.splitter, 1)

        target_row = QHBoxLayout()
        self.target_label = QLabel("Target: Screen (absolute)")
        self.target_label.setMinimumWidth(0)
        self.target_label.setMaximumWidth(255)
        self.target_label.setToolTip("Normal screen-wide macros remain unchanged.")
        target_row.addWidget(self.target_label, 1)
        self.target_pick = QPushButton("Choose window…")
        self.target_pick.clicked.connect(self.pick_target_window)
        target_row.addWidget(self.target_pick)
        self.target_clear = QPushButton("Clear target")
        self.target_clear.clicked.connect(lambda: self._set_window_target(None))
        self.target_clear.setEnabled(False)
        target_row.addWidget(self.target_clear)
        self.target_relative = QCheckBox("Client-relative coordinates")
        self.target_relative.setEnabled(False)
        self.target_relative.toggled.connect(self._target_options_changed)
        target_row.addWidget(self.target_relative)
        self.target_activate = QCheckBox("Activate before input")
        self.target_activate.setEnabled(False)
        self.target_activate.toggled.connect(self._target_options_changed)
        target_row.addWidget(self.target_activate)
        root.addLayout(target_row)

        status_row = QHBoxLayout()
        self.run_info = QLabel("Repeat")
        status_row.addWidget(self.run_info)
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 1000000)
        self.repeats.setValue(1)
        pad_spinbox_text(self.repeats)
        pad_spinbox_text(self.repeats)
        status_row.addWidget(self.repeats)
        status_row.addSpacing(12)
        status_row.addWidget(QLabel("Start delay (s)"))
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 3600)
        self.delay.setDecimals(1)
        self.delay.setValue(3.0)
        pad_spinbox_text(self.delay)
        pad_spinbox_text(self.delay)
        status_row.addWidget(self.delay)
        status_row.addSpacing(12)
        status_row.addWidget(QLabel("Debug gap (s)"))
        self.debug_gap = QDoubleSpinBox()
        self.debug_gap.setRange(0, 5)
        self.debug_gap.setDecimals(1)
        self.debug_gap.setSingleStep(0.1)
        self.debug_gap.setToolTip(
            "Extra delay between executable actions in this editor; not saved in macro JSON.")
        pad_spinbox_text(self.debug_gap)
        self.debug_gap.valueChanged.connect(
            lambda value: self.settings.setValue("debug_gap", value))
        status_row.addWidget(self.debug_gap)
        status_row.addSpacing(12)
        self.minimize_on_run = QCheckBox("Minimize when running")
        self.minimize_on_run.setToolTip(
            "Hide MacroRunner during playback and restore it when playback ends.")
        self.minimize_on_run.toggled.connect(
            lambda enabled: self.settings.setValue("minimize_on_run", enabled))
        status_row.addWidget(self.minimize_on_run)
        status_row.addStretch()
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(190)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        status_row.addWidget(self.progress_bar)
        root.addLayout(status_row)
        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status, 1)
        self._build_menus()
        self._update_controls()

    def _build_menus(self):
        menu = self.menuBar().addMenu("Edit")
        for name in ("undo", "redo", "breakpoint"):
            menu.addAction(self.toolbar_actions[name])
        menu.addSeparator()
        for title, slot, key in [
            ("Duplicate selection", self.duplicate, "Ctrl+D"),
            ("Delete selection", self.delete, "Delete"),
        ]:
            action = QAction(title, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            menu.addAction(action)
        view = self.menuBar().addMenu("View")
        dark = QAction("Dark theme", self, checkable=True)
        dark.setChecked(self.settings.value("theme", "dark") == "dark")
        dark.toggled.connect(lambda checked: self.set_theme("dark" if checked else "light"))
        view.addAction(dark)
        self.dark_action = dark
        view.addAction(self.toolbar_actions["history"])

        # A device preference, not part of the saved workflow. Hide by default
        # so screen targets behind the editor can be selected naturally.
        self.selection_mode_menu = view.addMenu("During screen selection")
        self.selection_mode_group = QActionGroup(self)
        self.selection_mode_group.setExclusive(True)
        for mode, label in (
            ("show", "Keep MacroRunner visible"),
            ("minimize", "Minimize MacroRunner"),
            ("hide", "Hide MacroRunner"),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(self._selection_window_mode() == mode)
            action.triggered.connect(
                lambda checked, selected=mode:
                    self.settings.setValue("selection_window_mode", selected)
            )
            self.selection_mode_group.addAction(action)
            self.selection_mode_menu.addAction(action)

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About MacroRunner", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_run_history(self):
        if self.run_history_dialog is None:
            dialog = RunHistoryDialog(self.diagnostics_store, self.settings, self)
            self.run_history_dialog = dialog
            dialog.finished.connect(self._history_dialog_closed)
        self.run_history_dialog.refresh()
        self.run_history_dialog.show()
        self.run_history_dialog.raise_()
        self.run_history_dialog.activateWindow()

    def _history_dialog_closed(self, _result):
        self.run_history_dialog = None

    def _diagnostic_event(self, event):
        if self._run_session is not None:
            self._run_session.add(event)
        if event.get("event") == "breakpoint" and self.executor is not None:
            index = event.get("index")
            item = self.tree.index_map().get(index)
            if item is not None:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
            self.toolbar_actions["pause"].setText("Resume")
            self._set_status(f"Breakpoint before action #{index + 1} — Resume or Step")
            if self._restore_after_run and self.isMinimized():
                # Make controls accessible, then minimize again when continuing,
                # so the target window is not hidden behind the editor.
                self._debug_window_visible = True
                self.showNormal()
                self.raise_()
                self.activateWindow()

    def _failure_capture_received(self, image):
        if self._run_session is not None:
            self._pending_failure_capture = image

    def show_about(self):
        QMessageBox.about(
            self, "About MacroRunner",
            f"<h3>MacroRunner v{app_version()}</h3>"
            "Structured mouse, keyboard, and screen-region automation.<br>"
            '<a href="https://github.com/kevinp260/macro-runner">GitHub repository</a>'
        )

    def _selection_window_mode(self):
        mode = self.settings.value("selection_window_mode", "hide")
        return mode if mode in ("show", "minimize", "hide") else "hide"

    def _restore_settings(self):
        self.set_theme(self.settings.value("theme", "dark"))
        self.minimize_on_run.setChecked(
            self.settings.value("minimize_on_run", False, type=bool))
        self.debug_gap.setValue(self.settings.value("debug_gap", 0.0, type=float))
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("splitter")
        if state is not None:
            self.splitter.restoreState(state)
        else:
            self.splitter.setSizes([205, 600, 365])

    def set_theme(self, name):
        app = QApplication.instance()
        app.setStyleSheet((DARK if name == "dark" else LIGHT) +
                          field_controls_style(name))
        self.settings.setValue("theme", name)

    def _filter_palette(self, text):
        for i in range(self.palette.count()):
            item = self.palette.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _set_status(self, text):
        self.status.setText(text)

    def _document_state(self):
        return (tuple(self.actions), self.repeats.value(), self.delay.value(),
                self.window_target)

    def _set_window_target(self, value):
        self.window_target = validate_target(value)
        bound = self.window_target is not None
        label = (f"Target: {self.window_target['title']}"
                 if bound else "Target: Screen (absolute)")
        self.target_label.setText(label)
        self.target_label.setToolTip(
            (f"Class: {self.window_target['class_name']} | "
             f"PID at selection: {self.window_target['pid']}"
             if bound else "Normal screen-wide macros remain unchanged."))
        self.target_clear.setEnabled(bound and not self._busy())
        for checkbox, option in ((self.target_relative, "relative"),
                                 (self.target_activate, "activate")):
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(bound and self.window_target[option]))
            checkbox.setEnabled(bound and not self._busy())
            checkbox.blockSignals(False)
        self._after_edit()

    def _target_options_changed(self, *_args):
        if self.window_target is None:
            return
        changed = dict(self.window_target)
        changed["relative"] = self.target_relative.isChecked()
        changed["activate"] = self.target_activate.isChecked()
        self._set_window_target(changed)

    def pick_target_window(self):
        if self._busy():
            return
        try:
            dialog = WindowPickerDialog(WindowManager(), self)
        except (WindowUnavailable, OSError) as exc:
            QMessageBox.warning(self, "Window targeting unavailable", str(exc))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected:
            self._set_window_target(target_from_window(dialog.selected))
            self._set_status("Target bound to selected window. Choose Save to persist it.")

    def _client_coordinates(self, x, y, width=None, height=None):
        if not self.window_target or not self.window_target["relative"]:
            return (x, y) if width is None else (x, y, width, height)
        binding = WindowBinding(self.window_target)
        info = binding.resolve()
        dx, dy = x - info.x, y - info.y
        if width is None:
            binding.point(dx, dy, info)
            return dx, dy
        binding.rect(dx, dy, width, height, info)
        return dx, dy, width, height

    def _is_dirty(self):
        return self._saved_state is None or self._document_state() != self._saved_state

    def _refresh_unsaved(self):
        name = Path(self.current_file).name if self.current_file else "Untitled workflow"
        self.setWindowTitle(("* " if self._is_dirty() else "") +
                            f"MacroRunner — {name}")

    def _recovery_error(self, error):
        if self._recovery_warning_shown:
            return
        self._recovery_warning_shown = True
        QMessageBox.warning(
            self, "Recovery unavailable",
            "MacroRunner could not update its local recovery snapshot. "
            "Your edits are still in memory; save your workflow to a file.\n\n"
            + str(error))

    def _clear_recovery(self):
        if self._recovery_locked:
            return
        try:
            self.recovery_store.clear()
        except OSError as exc:
            self._recovery_error(exc)

    def _write_recovery(self):
        if not self._is_dirty() or self._recovery_locked:
            return
        try:
            self.recovery_store.write(
                self.actions, self.repeats.value(), self.delay.value(),
                self.current_file or self._recovery_source_file,
                self.window_target)
            self._recovery_warning_shown = False
        except (OSError, ValueError, TypeError) as exc:
            self._recovery_error(exc)

    def _after_edit(self, *_args):
        self._refresh_unsaved()
        if self._is_dirty():
            if not self.recovery_timer.isActive():
                self.recovery_timer.start()
        else:
            self.recovery_timer.stop()
            self._clear_recovery()

    def _mark_clean(self):
        self._saved_state = deepcopy(self._document_state())
        self.recovery_timer.stop()
        self._refresh_unsaved()
        self._clear_recovery()

    def _confirm_unsaved(self):
        if not self._is_dirty():
            return True
        choice = QMessageBox.question(
            self, "Unsaved workflow",
            "Save changes to the current workflow before continuing?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save_workflow()
        return choice == QMessageBox.StandardButton.Discard

    def offer_recovery(self):
        """Called at startup, after the main window exists, before regular editing."""
        try:
            snapshot = self.recovery_store.read()
        except (OSError, ValueError, TypeError) as exc:
            choice = QMessageBox.question(
                self, "Recovery snapshot unreadable",
                "The local recovery file cannot be read. It might contain "
                "unsaved work.\n\n"
                "Discard the damaged snapshot to resume autosaving? "
                "Cancel keeps it untouched, but disables new recovery "
                "snapshots until that file is removed.\n\n" + str(exc),
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if choice == QMessageBox.StandardButton.Discard:
                self._clear_recovery()
                if self.recovery_store.path.exists():
                    self._recovery_locked = True
            else:
                self._recovery_locked = True
            return
        if snapshot is None:
            return
        source = snapshot.source_file or "Untitled workflow"
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Recover unsaved workflow?")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("A local autosave from an earlier session was found.")
        dialog.setInformativeText(
            f"Original file: {source}\nSnapshot (UTC): {snapshot.saved_at}\n\n"
            "Restore opens an unsaved copy. Your original file will NOT be "
            "overwritten; use Save to choose where to save the recovered work.")
        dialog.addButton("Restore", QMessageBox.ButtonRole.AcceptRole)
        discard = dialog.addButton("Discard recovery", QMessageBox.ButtonRole.DestructiveRole)
        dialog.exec()
        # Closing the prompt also restores, rather than risking a silent
        # overwrite of the existing snapshot during subsequent editing.
        if dialog.clickedButton() is not discard:
            self._replace_actions(snapshot.actions, remember=False)
            self.repeats.setValue(snapshot.repeat_count)
            self.delay.setValue(snapshot.start_delay)
            self._set_window_target(snapshot.window_target)
            self.current_file = None  # Recovery never silently writes the source.
            self._recovery_source_file = snapshot.source_file
            self.history = ActionHistory(60)
            self._saved_state = None
            self._after_edit()
            self._update_controls()
            self._set_status("Recovered as an unsaved workflow. Use Save to choose a file.")
        else:
            self._clear_recovery()

    def _busy(self):
        # Wait for the queued completion signal before allowing edits.
        return (self.recording or self.record_pending or self.executor is not None
                or self._screen_selection_active or self.region_monitor is not None)

    def _update_controls(self):
        busy = self._busy()
        running = self.executor is not None
        recording = self.recording or self.record_pending
        for key in ("new", "open", "save", "undo", "redo"):
            self.toolbar_actions[key].setEnabled(not busy)
        self.toolbar_actions["undo"].setEnabled(not busy and self.history.can_undo)
        self.toolbar_actions["redo"].setEnabled(not busy and self.history.can_redo)
        self.toolbar_actions["run"].setEnabled(not busy and bool(self.actions))
        self.toolbar_actions["pause"].setEnabled(running)
        self.toolbar_actions["stop"].setEnabled(busy)
        self.toolbar_actions["step"].setEnabled(not recording)
        self.toolbar_actions["run_from"].setEnabled(not busy and bool(self.actions))
        self.toolbar_actions["breakpoint"].setEnabled(not busy)
        self.toolbar_actions["record"].setEnabled(not busy or recording)
        self.toolbar_actions["record"].setText("Stop recording" if recording else "Record")
        self.tree.setEnabled(not busy)
        self.palette.setEnabled(not busy)
        self.inspector.setEnabled(not busy)
        self.repeats.setEnabled(not busy)
        self.delay.setEnabled(not busy)
        self.debug_gap.setEnabled(not busy)
        self.minimize_on_run.setEnabled(not busy)
        self.selection_mode_menu.setEnabled(not busy)
        self.target_pick.setEnabled(not busy)
        self.target_clear.setEnabled(not busy and self.window_target is not None)
        self.target_relative.setEnabled(not busy and self.window_target is not None)
        self.target_activate.setEnabled(not busy and self.window_target is not None)

    def _update_action_count(self, actions):
        disabled = sum(not action.enabled for action in actions
                       if action.kind not in CONTROL)
        summary = f"{len(actions)} raw actions"
        if disabled:
            summary += f" · {disabled} disabled"
        self.counter.setText(summary)

    def _changed(self, result):
        if result == self.actions:
            return
        self.history.record(self.actions)
        self.actions = result
        self._update_action_count(result)
        self._selection_changed()
        self._after_edit()
        self._update_controls()

    def _replace_actions(self, result, remember=True):
        if result == self.actions:
            return
        if remember:
            self.history.record(self.actions)
        self.actions = result
        self.tree.set_actions(result)
        self._update_action_count(result)
        self._selection_changed()
        self._after_edit()
        self._update_controls()

    def _selection_changed(self):
        self.inspector.show_action(self.tree.selected_action())

    def _apply_property(self, action):
        if self._busy():
            return
        try:
            self.tree.update_selected_action(action)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid edit", str(exc))

    def toggle_breakpoint(self):
        if not self._busy():
            self.tree.toggle_breakpoints()

    def delete(self):
        if not self._busy():
            self.tree.delete_selection()

    def duplicate(self):
        if not self._busy():
            self.tree.duplicate_selection()

    def undo(self):
        if self._busy():
            return
        result = self.history.undo(self.actions)
        if result is not None:
            self._replace_actions(result, remember=False)

    def redo(self):
        if self._busy():
            return
        result = self.history.redo(self.actions)
        if result is not None:
            self._replace_actions(result, remember=False)

    def new_workflow(self):
        if self._busy() or not self._confirm_unsaved():
            return
        self._replace_actions([], remember=False)
        self.history = ActionHistory(60)
        self.current_file = None
        self._recovery_source_file = None
        self._set_window_target(None)
        self.repeats.setValue(1)
        self.delay.setValue(3.0)
        self._mark_clean()
        self._update_controls()
        self._set_status("New workflow.")

    def open_workflow(self):
        if self._busy():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open workflow", "", "Macro files (*.json)")
        if not filename:
            return
        # Read and validate FIRST. A failed import must not discard edits or
        # recovery data from the current document.
        try:
            with open(filename, "r", encoding="utf-8") as file:
                actions, settings = parse_document(json.load(file))
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            QMessageBox.warning(self, "Cannot open macro", str(exc))
            return
        if not self._confirm_unsaved():
            return
        self._replace_actions(actions, remember=False)
        self.tree.clear_breakpoints()
        self.history = ActionHistory(60)
        if settings is not None:
            self.repeats.setValue(settings["repeat_count"])
            self.delay.setValue(settings["start_delay"])
        self._set_window_target(settings.get("window_target") if settings else None)
        self.current_file = filename
        self._recovery_source_file = None
        self._mark_clean()
        self._update_controls()
        self._set_status(f"Opened {os.path.basename(filename)}")

    def save_workflow(self):
        if self._busy():
            return False
        try:
            document = serialize_document(self.tree.actions(),
                                          self.repeats.value(), self.delay.value(),
                                          self.window_target)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid workflow", str(exc))
            return False
        filename = self.current_file
        if not filename:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save macro", "", "Macro files (*.json)")
        if not filename:
            return False
        try:
            # Also make normal saves atomic so a failed write never truncates
            # an existing workflow (the recovery file remains separate).
            atomic_json_write(filename, document)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Cannot save macro", str(exc))
            return False
        self.current_file = filename
        self._recovery_source_file = None
        self._mark_clean()
        self._set_status(f"Saved {os.path.basename(filename)}")
        return True

    def _validate_before_run(self, start_index):
        # Use the same physical coordinates as PyAutoGUI, not Qt's
        # DPI-scaled logical screen geometry. Checking size sends no input.
        screen_size = None
        try:
            import pyautogui
            dimensions = pyautogui.size()
            screen_size = (int(dimensions[0]), int(dimensions[1]))
        except Exception:
            # Restricted desktops may prevent geometry lookup; no unsupported
            # assumption about monitor bounds should block a workflow.
            pass
        findings = inspect_workflow(
            self.actions, start_index=start_index, screen_size=screen_size,
            session_type=os.environ.get("XDG_SESSION_TYPE"),
            window_target=self.window_target)
        if not findings:
            return True

        dialog = PreflightDialog(findings, self)
        approved = dialog.exec() == QDialog.DialogCode.Accepted
        if dialog.navigation_index is not None:
            item = self.tree.index_map().get(dialog.navigation_index)
            if item is not None:
                self.tree.clearSelection()
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
        return approved and not dialog.has_errors

    def _begin_run(self, start_selected=False, step_mode=False):
        if self._busy():
            return
        try:
            begin = self.tree.selected_flat_index() if (start_selected or step_mode) else 0
            repeats = 1 if (start_selected or step_mode) else self.repeats.value()
            if not self._validate_before_run(begin):
                return
            self.executor = MacroExecutor(
                self.actions, repeats, self.delay.value(),
                self.run_signals.progress.emit, self.run_signals.finished.emit,
                start_index=begin, step_mode=step_mode,
                breakpoints=self.tree.breakpoint_indices(), debug_gap=self.debug_gap.value(),
                window_target=self.window_target,
                clipboard=self.clipboard_client,
                on_diagnostic=self.run_signals.diagnostic.emit,
                on_failure_capture=(self.run_signals.failure_capture.emit
                    if self.settings.value("diagnostics_capture_errors", False, type=bool)
                    else None),
            )
            self._run_session = RunSession(
                self.actions,
                mode="step" if step_mode else ("selected" if start_selected else "full"),
                repeat_count=repeats)
            self._pending_failure_capture = None
            self._debug_window_visible = False
            # Hide the editor before the start delay begins. Restore only if
            # this run minimized the window, not if the user did so manually.
            self._restore_after_run = self.minimize_on_run.isChecked() and not self.isMinimized()
            if self._restore_after_run:
                self.showMinimized()
            try:
                self.executor.start()
            except Exception:
                self._restore_run_window()
                raise
            self.progress_bar.setRange(0, self.executor.total or 0)
            self.progress_bar.setValue(0)
            self._set_status("Paused — Step to advance" if step_mode else "Running…")
            self._update_controls()
        except (ValueError, RuntimeError) as exc:
            self.executor = None
            self._run_session = None
            self._pending_failure_capture = None
            QMessageBox.warning(self, "Unable to start", str(exc))

    def run_workflow(self):
        self._begin_run()

    def run_selected(self):
        if not self.tree.selectedItems():
            QMessageBox.information(self, "Select an action", "Select the action to start from.")
            return
        self._begin_run(start_selected=True)

    def _resume_debug_window(self):
        if self._debug_window_visible and self._restore_after_run:
            self._debug_window_visible = False
            self.showMinimized()

    def pause_run(self):
        if not self.executor or self._busy() and self.recording:
            return
        if self.executor.gate.paused:
            self._resume_debug_window()
            self.executor.resume()
            self.toolbar_actions["pause"].setText("Pause")
            self._set_status("Running…")
        else:
            self.executor.pause()
            self.toolbar_actions["pause"].setText("Resume")
            self._set_status("Paused")

    def step_run(self):
        if not self._busy():
            self._begin_run(step_mode=True)
        if self.executor and self.executor.gate.paused:
            try:
                self._resume_debug_window()
                self.executor.step()
                self._set_status("Stepping…")
            except RuntimeError:
                pass

    def stop_run(self):
        if self.recording or self.record_pending:
            self.stop_recording()
        elif self.executor:
            self.executor.stop()
            self._set_status("Stopping…")
        elif self.region_monitor is not None:
            self.region_monitor.stop_monitoring()
            self._set_status("Stopping screen-region test…")

    def _progress(self, cycle, cycles, action_index, completed, total):
        self._set_status(f"Run {cycle}/{cycles} · Action {completed}/{total or '?'}")
        if total is not None:
            self.progress_bar.setValue(min(completed, total))
        item = self.tree.index_map().get(action_index)
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _restore_run_window(self):
        self._debug_window_visible = False
        if self._restore_after_run:
            self._restore_after_run = False
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _finished(self, success, message):
        is_stopped = (not success and
                      (message == "Stopped." or
                       (self.executor is not None and
                        self.executor.gate.stopped.is_set())))
        status = "completed" if success else ("stopped" if is_stopped else "error")
        history_warning = False
        if self._run_session is not None:
            record = self._run_session.finish(status)
            capture = self._pending_failure_capture if status == "error" else None
            try:
                self.diagnostics_store.add(record, capture=capture)
            except (OSError, ValueError):
                history_warning = True
            if self.run_history_dialog is not None:
                self.run_history_dialog.refresh()
        self._run_session = None
        self._pending_failure_capture = None
        self.executor = None
        self._restore_run_window()
        self.toolbar_actions["pause"].setText("Pause")
        self._set_status(
            message + (" Warning: run history could not be saved."
                       if history_warning else ""))
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if success else 0)
        self._update_controls()
        if not success:
            QMessageBox.warning(self, "Workflow stopped", message)

    def _test_monitoring(self, action):
        """Preview the current inspector settings, without editing the macro."""
        if self._busy():
            return
        dialog = RegionMonitorDialog(action)  # Independent window: stays visible if editor minimizes.
        self.region_monitor = dialog
        self._monitor_restore_state = None
        dialog.finished.connect(self._monitor_closed)
        self._set_status("Testing screen-region detection (read-only).")
        self._update_controls()
        dialog.show()
        dialog.position_away_from_region()
        # Match the playback visibility preference; screen-selection visibility
        # controls picking, not this live test. The preview itself remains shown.
        if (self.minimize_on_run.isChecked() and self.isVisible()
                and not self.isMinimized()):
            self._monitor_restore_state = self.windowState()
            self.showMinimized()
        dialog.raise_()
        dialog.activateWindow()
        QTimer.singleShot(
            160,
            lambda: dialog.start_monitoring()
            if self.region_monitor is dialog and dialog.isVisible() else None,
        )

    def _monitor_closed(self, _result):
        dialog = self.region_monitor
        self.region_monitor = None
        state = self._monitor_restore_state
        self._monitor_restore_state = None
        if state is not None and not self._close_after_monitor:
            if state & Qt.WindowState.WindowFullScreen:
                self.showFullScreen()
            elif state & Qt.WindowState.WindowMaximized:
                self.showMaximized()
            else:
                self.showNormal()
            self.raise_()
            self.activateWindow()
        if dialog is not None:
            dialog.deleteLater()
        self._update_controls()
        if self._close_after_monitor:
            self._close_after_monitor = False
            QTimer.singleShot(0, self.close)
        else:
            self._set_status("Screen-region test closed.")

    def _test_move(self, x, y):
        if self._busy():
            return
        try:
            import pyautogui
            if self.window_target and self.window_target["relative"]:
                binding = WindowBinding(self.window_target)
                info = binding.resolve()
                x, y = binding.point(x, y, info)
            pyautogui.moveTo(x, y, duration=.15)
            self._set_status(f"Moved pointer to ({x}, {y}).")
        except Exception as exc:
            QMessageBox.warning(self, "Mouse movement unavailable", str(exc))

    def _begin_screen_selection(self):
        """Temporarily change editor visibility for a point or region pick."""
        if self._busy():
            return False
        self._screen_selection_active = True
        self._screen_selection_restore = None
        mode = self._selection_window_mode()
        # Do not reveal a window that was already hidden or minimized.
        if self.isVisible() and not self.isMinimized() and mode != "show":
            self._screen_selection_restore = self.windowState()
            if mode == "minimize":
                self.showMinimized()
            else:
                self.hide()
        self._update_controls()
        return True

    def _end_screen_selection(self, restore=True):
        if not self._screen_selection_active:
            return
        state = self._screen_selection_restore
        self._screen_selection_active = False
        self._screen_selection_restore = None
        if restore and state is not None:
            if state & Qt.WindowState.WindowFullScreen:
                self.showFullScreen()
            elif state & Qt.WindowState.WindowMaximized:
                self.showMaximized()
            else:
                self.showNormal()
            self.raise_()
            self.activateWindow()
        self._update_controls()

    def _pick_region(self):
        if not self._begin_screen_selection():
            return
        self._set_status("Drag to select a region · Esc to cancel.")

        def selected(x, y, width, height):
            self.region_picker = None
            self._end_screen_selection()
            try:
                rx, ry, rw, rh = self._client_coordinates(x, y, width, height)
                self.inspector.update_picked_region(rx, ry, rw, rh)
                self._set_status(
                    f"Selected region ({rx}, {ry}), {rw}×{rh}. "
                    "Choose Apply changes to save.")
            except (WindowUnavailable, ValueError) as exc:
                QMessageBox.warning(self, "Region outside target window", str(exc))

        def cancelled():
            self.region_picker = None
            self._end_screen_selection()
            self._set_status("Region selection cancelled.")

        def launch():
            if not self._screen_selection_active:
                return
            try:
                self.region_picker = RegionPicker(selected, cancelled)
                self.region_picker.show()
            except Exception as exc:
                if self.region_picker is not None:
                    self.region_picker.cancel(notify=False)
                    self.region_picker = None
                self._end_screen_selection()
                QMessageBox.warning(self, "Region selection unavailable", str(exc))

        # Let the window manager finish hiding/minimizing the editor before
        # displaying the overlay (important on Windows and composited desktops).
        QTimer.singleShot(150, launch)

    def _pick_coordinates(self, mode):
        if not self._begin_screen_selection():
            return
        self._set_status("Move the pointer to the target — capturing in 3 seconds…")

        def finish():
            if not self._screen_selection_active:
                return
            error = None
            try:
                import pyautogui
                x, y = pyautogui.position()
                color = None
                if mode == "pixel":
                    rgb = pyautogui.screenshot(region=(x, y, 1, 1)).convert("RGB").getpixel((0, 0))
                    color = "#{:02X}{:02X}{:02X}".format(*rgb)
                x, y = self._client_coordinates(x, y)
                self.inspector.update_picked_coordinates(mode, x, y, color)
                self._set_status(f"Captured ({x}, {y}). Choose Apply changes to save.")
            except Exception as exc:
                error = exc
            finally:
                self._end_screen_selection()
            if error is not None:
                QMessageBox.warning(self, "Screen capture unavailable", str(error))

        QTimer.singleShot(3000, finish)

    def _start_hotkeys(self):
        try:
            from pynput import keyboard
            self.hotkeys = keyboard.GlobalHotKeys({
                "<ctrl>+<alt>+<shift>+<f6>": self.global_pause.emit,
                "<ctrl>+<alt>+<shift>+<f8>": self.global_stop.emit,
            })
            self.hotkeys.start()
        except Exception:
            self.hotkeys = None
            self._set_status("Global hotkeys unavailable in this desktop session.")

    def _capture_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Record actions")
        form = QFormLayout(dialog)
        keyboard_toggle = QCheckBox("Also record keyboard events (sensitive)")
        form.addRow(keyboard_toggle)
        wait_toggle = QCheckBox("Insert waits between actions")
        wait_toggle.setChecked(True)
        form.addRow(wait_toggle)
        min_wait = QDoubleSpinBox()
        min_wait.setRange(0, 30)
        min_wait.setSingleStep(.1)
        min_wait.setValue(.3)
        form.addRow("Minimum wait (s)", min_wait)
        repetitions = QSpinBox()
        repetitions.setRange(1, 100000)
        form.addRow("Recorded mouse click repeats", repetitions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return (keyboard_toggle.isChecked(), wait_toggle.isChecked(),
                min_wait.value(), repetitions.value())

    def record_toggle(self):
        if self.recording or self.record_pending:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        if self._busy():
            return
        settings = self._capture_settings()
        if settings is None:
            return
        if settings[0] and QMessageBox.question(
            self, "Keyboard privacy",
            "Keyboard recording captures input from OTHER applications, "
            "including passwords. Only use it in a harmless test application. "
            "Continue?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self.capture_keyboard, self.capture_waits, self.capture_min_wait, self.capture_repeats = settings
        self.capture_last = None
        self.capture_history = True
        self.capture_token += 1
        token = self.capture_token
        self.record_pending = True
        self._set_status("Recording begins in 3 seconds…")
        self._update_controls()
        QTimer.singleShot(3000, lambda: self._activate_recording(token))

    def _activate_recording(self, token):
        if not self.record_pending or token != self.capture_token:
            return
        self.record_pending = False
        self.recording = True
        self.keyboard_recorder = KeyboardRecorder() if self.capture_keyboard else None
        try:
            from pynput import mouse, keyboard

            def on_click(x, y, button, pressed):
                if pressed:
                    self.events.put((time.monotonic(), token, "click", int(x), int(y),
                                     str(button).rsplit(".", 1)[-1].lower()))

            self.mouse_listener = mouse.Listener(on_click=on_click)
            self.mouse_listener.start()

            if self.capture_keyboard:
                def on_press(key):
                    name = normalize_event_key(key)
                    if name:
                        self.events.put((time.monotonic(), token, "key", name, True))
                def on_release(key):
                    name = normalize_event_key(key)
                    if name:
                        self.events.put((time.monotonic(), token, "key", name, False))
                self.keyboard_listener = keyboard.Listener(
                    on_press=on_press, on_release=on_release)
                self.keyboard_listener.start()
            self._set_status("Recording… click Stop recording when finished.")
        except Exception as exc:
            self.stop_recording()
            QMessageBox.warning(self, "Recording unavailable", str(exc))
        self._update_controls()

    def _append_recorded(self, action, timestamp):
        if self.capture_history:
            self.history.record(self.actions)
            self.capture_history = False
        updated = list(self.actions)
        if self.capture_waits and self.capture_last is not None:
            gap = timestamp - self.capture_last
            if gap >= self.capture_min_wait:
                updated.append(Action(kind="wait", seconds=round(gap, 3)))
        self.capture_last = timestamp
        updated.append(action)
        self.actions = updated
        self.tree.set_actions(updated)
        self.counter.setText(f"{len(updated)} raw actions")
        self._after_edit()

    def _drain_capture(self):
        events = []
        while True:
            try:
                events.append(self.events.get_nowait())
            except queue.Empty:
                break
        events.sort(key=lambda event: event[0])
        for event in events:
            timestamp, token, kind, *data = event
            if token != self.capture_token or not self.recording:
                continue
            if kind == "click":
                x, y, button = data
                if button not in ("left", "right", "middle"):
                    continue
                if self.frameGeometry().contains(QPoint(x, y)):
                    continue
                self._append_recorded(Action(kind="click", x=x, y=y,
                                             button=button,
                                             repeats=self.capture_repeats), timestamp)
            elif kind == "key" and self.keyboard_recorder is not None:
                # Input within MacroRunner itself must never be recorded.
                if QApplication.activeWindow() is self:
                    continue
                name, pressed = data
                action = (self.keyboard_recorder.press(name) if pressed
                          else self.keyboard_recorder.release(name))
                if action:
                    self._append_recorded(action, timestamp)
        self._update_controls()

    def stop_recording(self):
        if not self.recording and not self.record_pending:
            return
        self.record_pending = False
        for name in ("mouse_listener", "keyboard_listener"):
            listener = getattr(self, name)
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
                setattr(self, name, None)
        if self.recording:
            self._drain_capture()
        if self.keyboard_recorder is not None:
            for action in self.keyboard_recorder.finish():
                self._append_recorded(action, time.monotonic())
        self.keyboard_recorder = None
        self.recording = False
        self.capture_token += 1
        self.capture_history = False
        self._set_status("Recording finished.")
        self._update_controls()

    def closeEvent(self, event):
        if self.recording:
            self._drain_capture()
        if not self._confirm_unsaved():
            event.ignore()
            return
        if self.region_monitor is not None:
            self._close_after_monitor = True
            self.region_monitor.close()
            if self.region_monitor is not None:
                event.ignore()
                return
        if self.region_picker is not None:
            self.region_picker.cancel(notify=False)
            self.region_picker = None
        # Invalidate any delayed selection callbacks without reopening the UI.
        self._end_screen_selection(restore=False)
        if self.recording or self.record_pending:
            self.stop_recording()
        if self.executor is not None:
            self.executor.stop()
            if self.executor.thread is not None:
                self.executor.thread.join(timeout=2)
                if self.executor.thread.is_alive():
                    event.ignore()
                    QMessageBox.warning(
                        self, "Workflow still stopping",
                        "MacroRunner is still stopping the active action. "
                        "Please close again after the action finishes.")
                    return
        if self.hotkeys:
            self.hotkeys.stop()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.splitter.saveState())
        self.recovery_timer.stop()
        self._clear_recovery()
        event.accept()


def _windows_single_instance():
    """Keep the Windows installer mutex held while the application runs."""
    if sys.platform != "win32":
        return None, False

    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, "Global\MacroRunnerMutex")
    if not handle:
        raise OSError(ctypes.get_last_error(), "Cannot create MacroRunner mutex")
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        return None, True
    return (kernel, handle), False


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MacroRunner")
    app.setOrganizationName("MacroRunner")
    app.setApplicationVersion(app_version())
    mutex, already_running = _windows_single_instance()
    if already_running:
        QMessageBox.warning(None, "Already running", "MacroRunner is already running.")
        return 0
    try:
        window = MacroWindow()
        window.show()
        window.offer_recovery()
        return app.exec()
    finally:
        if mutex is not None:
            kernel, handle = mutex
            kernel.CloseHandle(handle)
