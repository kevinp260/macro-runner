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

from PySide6.QtCore import Qt, QSettings, QTimer, QObject, Signal, QPoint
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QToolBar, QLabel, QPushButton, QFileDialog, QMessageBox,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QProgressBar, QAbstractItemView
)

from macro_model import Action, parse_document, serialize_document
from macro_editing import ActionHistory
from macro_qt_workflow import ActionPalette, WorkflowTree, KINDS
from macro_qt_properties import PropertiesPanel
from macro_runtime import MacroExecutor
from macro_keys import KeyboardRecorder, normalize_event_key


DARK = """
QMainWindow, QWidget { background: #15191f; color: #e6eaf0; }
QLabel#panelHeading { font-size: 16px; font-weight: 700; }
QLabel#muted { color: #94a1b1; }
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
QSplitter::handle { background: #303a49; width: 5px; }
QStatusBar { background: #1b222c; color: #b8c8d8; }
QScrollBar:vertical { background: #202834; width: 11px; }
QScrollBar::handle:vertical { background: #4a596c; border-radius: 5px; }
QCheckBox { spacing: 8px; }
"""
LIGHT = """
QMainWindow, QWidget { background: #f4f6f9; color: #263344; }
QLabel#panelHeading { font-size: 16px; font-weight: 700; }
QLabel#muted { color: #68788a; }
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
QSplitter::handle { background: #dce3ea; width: 5px; }
QStatusBar { background: white; color: #4c5b6d; }
"""


class WorkerSignals(QObject):
    progress = Signal(int, int, int, int, object)
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
        self.setMinimumSize(780, 520)
        self.resize(1180, 760)
        self.settings = QSettings("MacroRunner", "Desktop")
        self.actions = []
        self.history = ActionHistory(60)
        self.current_file = None
        self.executor = None
        self.run_signals = WorkerSignals()
        self.run_signals.progress.connect(self._progress)
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
        self._build_ui()
        self._restore_settings()
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

        palette_panel = QFrame()
        palette_panel.setObjectName("panel")
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
        editor_layout = QVBoxLayout(editor_panel)
        title_row = QHBoxLayout()
        label = QLabel("Workflow")
        label.setObjectName("panelHeading")
        title_row.addWidget(label)
        title_row.addStretch()
        self.counter = QLabel("0 actions")
        self.counter.setObjectName("muted")
        title_row.addWidget(self.counter)
        editor_layout.addLayout(title_row)
        self.tree = WorkflowTree()
        self.tree.actions_changed.connect(self._changed)
        self.tree.invalid_change.connect(
            lambda text: QMessageBox.warning(self, "Invalid workflow structure", text))
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        editor_layout.addWidget(self.tree, 1)

        buttons = QHBoxLayout()
        for text, handler in [
            ("Duplicate", self.duplicate), ("Delete", self.delete),
            ("Collapse all", self.tree.collapseAll),
            ("Expand all", self.tree.expandAll),
        ]:
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        editor_layout.addLayout(buttons)
        self.splitter.addWidget(editor_panel)

        self.inspector = PropertiesPanel()
        self.inspector.apply_action.connect(self._apply_property)
        self.inspector.pick_coordinates.connect(self._pick_coordinates)
        self.inspector.test_move.connect(self._test_move)
        self.splitter.addWidget(self.inspector)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        root.addWidget(self.splitter, 1)

        status_row = QHBoxLayout()
        self.run_info = QLabel("Repeat")
        status_row.addWidget(self.run_info)
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 1000000)
        self.repeats.setValue(1)
        status_row.addWidget(self.repeats)
        status_row.addSpacing(12)
        status_row.addWidget(QLabel("Start delay (s)"))
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 3600)
        self.delay.setDecimals(1)
        self.delay.setValue(3.0)
        status_row.addWidget(self.delay)
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
        for name in ("undo", "redo"):
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

    def _restore_settings(self):
        self.set_theme(self.settings.value("theme", "dark"))
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("splitter")
        if state is not None:
            self.splitter.restoreState(state)
        else:
            self.splitter.setSizes([220, 600, 340])

    def set_theme(self, name):
        app = QApplication.instance()
        app.setStyleSheet(DARK if name == "dark" else LIGHT)
        self.settings.setValue("theme", name)

    def _filter_palette(self, text):
        for i in range(self.palette.count()):
            item = self.palette.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _set_status(self, text):
        self.status.setText(text)

    def _busy(self):
        return self.recording or self.record_pending or (
            self.executor is not None and self.executor.thread is not None
            and self.executor.thread.is_alive()
        )

    def _update_controls(self):
        busy = self._busy()
        running = self.executor is not None and self.executor.thread is not None and (
            self.executor.thread.is_alive()
        )
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
        self.toolbar_actions["record"].setEnabled(not running)
        self.toolbar_actions["record"].setText("Stop recording" if recording else "Record")
        self.tree.setEnabled(not busy)
        self.palette.setEnabled(not busy)
        self.inspector.setEnabled(not busy)
        self.repeats.setEnabled(not busy)
        self.delay.setEnabled(not busy)

    def _changed(self, result):
        if result == self.actions:
            return
        self.history.record(self.actions)
        self.actions = result
        self.counter.setText(f"{len(result)} raw actions")
        self._selection_changed()
        self._update_controls()

    def _replace_actions(self, result, remember=True):
        if result == self.actions:
            return
        if remember:
            self.history.record(self.actions)
        self.actions = result
        self.tree.set_actions(result)
        self.counter.setText(f"{len(result)} raw actions")
        self._selection_changed()
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
        if self._busy():
            return
        if self.actions and QMessageBox.question(
            self, "New workflow", "Discard the current workflow?",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._replace_actions([])
        self.current_file = None
        self.repeats.setValue(1)
        self.delay.setValue(3.0)

    def open_workflow(self):
        if self._busy():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open workflow", "", "Macro files (*.json)")
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as file:
                actions, settings = parse_document(json.load(file))
            self._replace_actions(actions)
            if settings is not None:
                self.repeats.setValue(settings["repeat_count"])
                self.delay.setValue(settings["start_delay"])
            self.current_file = filename
            self._set_status(f"Opened {os.path.basename(filename)}")
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Cannot open macro", str(exc))

    def save_workflow(self):
        if self._busy():
            return
        try:
            document = serialize_document(self.tree.actions(),
                                          self.repeats.value(), self.delay.value())
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid workflow", str(exc))
            return
        filename = self.current_file
        if not filename:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save macro", "", "Macro files (*.json)")
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(document, file, indent=2)
            self.current_file = filename
            self._set_status(f"Saved {os.path.basename(filename)}")
        except OSError as exc:
            QMessageBox.warning(self, "Cannot save macro", str(exc))

    def _begin_run(self, start_selected=False, step_mode=False):
        if self._busy():
            return
        try:
            begin = self.tree.selected_flat_index() if (start_selected or step_mode) else 0
            repeats = 1 if (start_selected or step_mode) else self.repeats.value()
            self.executor = MacroExecutor(
                self.actions, repeats, self.delay.value(),
                self.run_signals.progress.emit, self.run_signals.finished.emit,
                start_index=begin, step_mode=step_mode,
            )
            self.executor.start()
            self.progress_bar.setRange(0, self.executor.total or 0)
            self.progress_bar.setValue(0)
            self._set_status("Paused — Step to advance" if step_mode else "Running…")
            self._update_controls()
        except (ValueError, RuntimeError) as exc:
            self.executor = None
            QMessageBox.warning(self, "Unable to start", str(exc))

    def run_workflow(self):
        self._begin_run()

    def run_selected(self):
        if not self.tree.selectedItems():
            QMessageBox.information(self, "Select an action", "Select the action to start from.")
            return
        self._begin_run(start_selected=True)

    def pause_run(self):
        if not self.executor or self._busy() and self.recording:
            return
        if self.executor.gate.paused:
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

    def _progress(self, cycle, cycles, action_index, completed, total):
        self._set_status(f"Run {cycle}/{cycles} · Action {completed}/{total or '?'}")
        if total is not None:
            self.progress_bar.setValue(min(completed, total))
        item = self.tree.index_map().get(action_index)
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _finished(self, success, message):
        self.executor = None
        self.toolbar_actions["pause"].setText("Pause")
        self._set_status(message)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1 if success else 0)
        self._update_controls()
        if not success:
            QMessageBox.warning(self, "Workflow stopped", message)

    def _test_move(self, x, y):
        if self._busy():
            return
        try:
            import pyautogui
            pyautogui.moveTo(x, y, duration=.15)
            self._set_status(f"Moved pointer to ({x}, {y}).")
        except Exception as exc:
            QMessageBox.warning(self, "Mouse movement unavailable", str(exc))

    def _pick_coordinates(self, mode):
        if self._busy():
            return
        self._set_status("Move the pointer to the target — capturing in 3 seconds…")

        def finish():
            if self._busy():
                return
            try:
                import pyautogui
                x, y = pyautogui.position()
                color = None
                if mode == "pixel":
                    rgb = pyautogui.screenshot(region=(x, y, 1, 1)).convert("RGB").getpixel((0, 0))
                    color = "#{:02X}{:02X}{:02X}".format(*rgb)
                self.inspector.update_picked_coordinates(mode, x, y, color)
                self._set_status(f"Captured ({x}, {y}). Choose Apply changes to save.")
            except Exception as exc:
                QMessageBox.warning(self, "Screen capture unavailable", str(exc))

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
        event.accept()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("MacroRunner")
    app.setOrganizationName("MacroRunner")
    window = MacroWindow()
    window.show()
    return app.exec()
