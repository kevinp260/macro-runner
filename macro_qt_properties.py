"""Scrollable, schema-driven Qt action inspector."""
from dataclasses import asdict

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QPushButton, QLabel, QFileDialog, QHBoxLayout,
    QMessageBox, QFrame, QPlainTextEdit, QDialog
)

from macro_model import Action, validate_action
from macro_flow import CONTROL
from macro_windows import WindowManager, WindowUnavailable
from macro_qt_windows import WindowPickerDialog
from macro_variables import BINDABLE

# Describes only fields that are relevant to an action kind.
SPECS = {
    "click": ["x", "y", "button", "clicks", "interval"],
    "click_image": ["button", "image_offset_x", "image_offset_y",
                    "timeout", "poll_interval"],
    "wait": ["seconds"],
    "wait_until": ["timeout", "poll_interval"],
    "find_text": ["text_target", "text_language", "text_confidence", "text_click",
                  "region_x", "region_y", "region_w", "region_h"],
    "wait_text": ["text_target", "text_language", "text_confidence",
                  "region_x", "region_y", "region_w", "region_h",
                  "timeout", "poll_interval"],
    "key": ["key_mode", "keys"],
    "key_down": ["keys"],
    "key_up": ["keys"],
    "move": ["x", "y", "move_duration"],
    "scroll": ["scroll_amount"],
    "drag": ["x", "y", "to_x", "to_y", "move_duration", "button"],
    "clipboard_set": ["clipboard_text"],
    "clipboard_paste": ["clipboard_text", "clipboard_restore"],
    "clipboard_read": [],
    "launch": ["launch_mode", "launch_target", "launch_args"],
    "wait_window": ["window_wait_source", "window_wait_state",
                    "window_wait_title", "window_wait_class",
                    "timeout", "poll_interval"],
    "file_check": ["file_path"],
    "file_wait": ["file_path", "timeout", "poll_interval"],
    "file_copy": ["file_path", "file_destination", "file_overwrite"],
    "file_move": ["file_path", "file_destination", "file_overwrite"],
    "folder_create": ["file_path"],
    "loop_start": [],
    "if_start": [],
    "until_start": [],
    "watch_start": ["region_x", "region_y", "region_w", "region_h",
                    "poll_interval", "watch_change_percent",
                    "watch_pixel_tolerance", "watch_confirmations",
                    "watch_max_changes"],
}
VISUAL = frozenset(("click_image", "wait_until", "if_start", "until_start"))
IMAGE_FIELDS = ["image_path", "confidence", "region_x", "region_y", "region_w", "region_h"]
PIXEL_FIELDS = ["pixel_x", "pixel_y", "pixel_color", "pixel_tolerance"]
VISUAL_FIELDS = ["condition_source", "match_mode"] + IMAGE_FIELDS + PIXEL_FIELDS
COMBOS = {
    "button": ["left", "right", "middle"],
    "key_mode": ["press", "type"],
    "condition_source": ["image", "pixel"],
    "match_mode": ["matches", "not_matches"],
    "failure_policy": ["stop", "skip", "retry"],
    "launch_mode": ["application", "file", "url"],
    "window_wait_source": ["custom", "workflow"],
    "window_wait_state": ["appears", "active", "hidden", "closed"],
}
INTEGER = frozenset(("x", "y", "to_x", "to_y", "clicks", "scroll_amount",
                     "pixel_x", "pixel_y", "pixel_tolerance",
                     "region_x", "region_y", "region_w", "region_h",
                     "watch_pixel_tolerance", "watch_confirmations",
                     "watch_max_changes", "retry_count", "image_offset_x", "image_offset_y"))
FLOAT = frozenset(("interval", "seconds", "move_duration", "timeout",
                   "poll_interval", "confidence", "watch_change_percent",
                   "retry_delay", "text_confidence"))
OPTIONAL = frozenset(("region_x", "region_y", "region_w", "region_h"))


def pad_spinbox_text(spinbox, left=11):
    """Inset the actual numeric editor, not only its outer Qt stylesheet box.

    QSpinBox/QDoubleSpinBox render their value through an embedded QLineEdit.
    The parent widget's QSS padding does not reliably move that text on all
    Qt platform styles (notably Linux/XCB).
    """
    editor = spinbox.findChild(QLineEdit)
    if editor is not None:
        editor.setTextMargins(left, 0, 0, 0)


def pad_spinbox_text(spinbox, left=11):
    """Inset the embedded numeric editor, not just the outer Qt widget."""
    editor = spinbox.findChild(QLineEdit)
    if editor is not None:
        editor.setTextMargins(left, 0, 0, 0)


def fields_for_kind(kind):
    fields = list(SPECS.get(kind, []))
    if kind in VISUAL:
        fields.extend(VISUAL_FIELDS)
    if kind not in CONTROL:
        fields.append("failure_policy")
        if kind in ("click_image", "wait_until", "wait_text"):
            fields.extend(("retry_count", "retry_delay"))
    return fields


def convert(field, text):
    if field in OPTIONAL and not str(text).strip():
        return None
    if field in INTEGER:
        return int(text)
    if field in FLOAT:
        return float(text)
    return text


class PropertiesPanel(QFrame):
    apply_action = Signal(object)
    pick_coordinates = Signal(str)
    test_move = Signal(int, int)
    pick_region = Signal()
    test_monitoring = Signal(object)
    preview_image_click = Signal(object)
    preview_text = Signal(object)
    test_launch = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        # The inspector needs room for both labels and inputs (plus browse).
        self.setMinimumWidth(350)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)
        self.heading = QLabel("Properties")
        self.heading.setObjectName("panelHeading")
        outer.addWidget(self.heading)
        self.hint = QLabel("Select an action to inspect and edit it.")
        self.hint.setObjectName("panelHint")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll, 1)
        self.content = QWidget()
        self.form = QFormLayout(self.content)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.form.setSpacing(12)
        self.scroll.setWidget(self.content)
        self.controls = {}
        self.current = None
        self.apply = QPushButton("Apply changes")
        self.apply.setObjectName("primaryButton")
        self.apply.clicked.connect(self.commit)
        outer.addWidget(self.apply)
        self.show_action(None)

    def _reset_form(self):
        while self.form.count():
            item = self.form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                layout = item.layout()
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        self.controls = {}

    def show_action(self, action, variables=None):
        self.current = action
        self.variable_definitions = variables or []
        self._reset_form()
        self.variable_controls = {}
        self.result_picker = None
        self._wait_identity = (
            (action.window_wait_handle, action.window_wait_pid)
            if action is not None and action.kind == "wait_window"
            else (0, 0))
        if action is None:
            self.hint.setText("Select an action in the workflow.")
            self.apply.setEnabled(False)
            return
        self.apply.setEnabled(True)
        self.heading.setText(action.name or action.kind.replace("_", " ").title())
        self.hint.setText(action.kind.replace("_", " ").title() +
                          " · Edit the fields below, then choose Apply changes.")
        name = QLineEdit(action.name)
        name.setPlaceholderText("Optional label")
        self.controls["name"] = name
        self.form.addRow("Name", name)
        if action.kind not in CONTROL or action.kind in ("loop_start", "until_start"):
            repeats = QSpinBox()
            repeats.setRange(1, 1000000)
            repeats.setValue(action.repeats)
            pad_spinbox_text(repeats)
            pad_spinbox_text(repeats)
            self.controls["repeats"] = repeats
            self.form.addRow("Repeat count", repeats)
        if action.kind not in CONTROL:
            enabled = QCheckBox("Enabled")
            enabled.setChecked(action.enabled)
            self.controls["enabled"] = enabled
            self.form.addRow("", enabled)
        for field in fields_for_kind(action.kind):
            value = getattr(action, field)
            if field == "launch_args":
                widget = QPlainTextEdit()
                widget.setPlainText(value)
                widget.setPlaceholderText(
                    "One argument per line. Spaces and Unicode stay intact. "
                    "No quoting or shell syntax.")
                widget.setMaximumHeight(100)
                self.controls[field] = widget
                self.form.addRow("Arguments", widget)
                continue
            if field == "clipboard_text":
                widget = QPlainTextEdit()
                widget.setPlainText("" if value is None else value)
                widget.setMaximumHeight(110)
                widget.setPlaceholderText(
                    "Leave blank to paste existing clipboard text."
                    if action.kind == "clipboard_paste"
                    else "Text to place on the clipboard. Blank clears text.")
                self.controls[field] = widget
                self.form.addRow("Clipboard text", widget)
                continue
            if field == "file_overwrite":
                widget = QCheckBox("Replace an existing destination file")
                widget.setChecked(value)
                self.controls[field] = widget
                self.form.addRow("", widget)
                continue
            if field == "text_click":
                widget = QCheckBox("Click center of recognized phrase")
                widget.setChecked(bool(value))
                self.controls[field] = widget
                self.form.addRow("", widget)
                continue
            if field == "clipboard_restore":
                widget = QCheckBox("Restore previous clipboard text after paste")
                widget.setChecked(bool(value))
                self.controls[field] = widget
                self.form.addRow("", widget)
                continue
            if field in COMBOS:
                widget = QComboBox()
                widget.addItems(COMBOS[field])
                widget.setCurrentText(str(value))
            else:
                widget = QLineEdit("" if value is None else str(value))
                if field == "text_target":
                    widget.setPlaceholderText("Exact words or phrase (case-insensitive)")
                elif field == "text_language":
                    widget.setPlaceholderText("e.g. eng or eng+deu")
                if field in ("file_path", "file_destination"):
                    row = QWidget()
                    layout = QHBoxLayout(row)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.addWidget(widget, 1)
                    browse = QPushButton("Browse…")
                    browse.clicked.connect(
                        lambda _, target=widget, part=field:
                        self.browse_file_action(target, part))
                    layout.addWidget(browse)
                    label = ("Destination file" if field == "file_destination"
                             else "Folder path" if action.kind == "folder_create"
                             else "File path" if action.kind in
                                  ("file_check", "file_wait")
                             else "Source file")
                    self.form.addRow(label, row)
                    self.controls[field] = widget
                    continue
                if field == "window_wait_title":
                    row = QWidget()
                    layout = QHBoxLayout(row)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.addWidget(widget, 1)
                    pick = QPushButton("Choose…")
                    pick.clicked.connect(self.pick_wait_window)
                    layout.addWidget(pick)
                    self.wait_pick = pick
                    widget.textEdited.connect(self._forget_wait_identity)
                    self.form.addRow("Exact window title", row)
                    self.controls[field] = widget
                    continue
                if field == "window_wait_class":
                    widget.setPlaceholderText("Optional class filter")
                    widget.textEdited.connect(self._forget_wait_identity)
                if field == "launch_target":
                    row = QWidget()
                    layout = QHBoxLayout(row)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.addWidget(widget, 1)
                    browse = QPushButton("Browse…")
                    browse.clicked.connect(lambda _, target=widget: self.browse_launch(target))
                    layout.addWidget(browse)
                    self.launch_browse = browse
                    self.form.addRow("Path or URL", row)
                    self.controls[field] = widget
                    continue
                if field == "image_path":
                    row = QWidget()
                    layout = QHBoxLayout(row)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.addWidget(widget, 1)
                    browse = QPushButton("Browse…")
                    browse.clicked.connect(lambda _, target=widget: self.browse_image(target))
                    layout.addWidget(browse)
                    self.form.addRow("Reference image", row)
                    self.controls[field] = widget
                    continue
            self.controls[field] = widget
            self.form.addRow(field.replace("_", " ").capitalize(), widget)
        if action.kind in ("click_image", "clipboard_read"):
            expected = ("coordinates" if action.kind == "click_image" else "text")
            picker = QComboBox()
            picker.addItem("Do not save match" if action.kind == "click_image"
                           else "Choose a text variable", "")
            for item in self.variable_definitions:
                if item["type"] == expected:
                    picker.addItem(item["name"], item["name"])
            if action.result_variable and picker.findData(action.result_variable) < 0:
                picker.addItem(action.result_variable + " (unavailable)",
                               action.result_variable)
            picker.setCurrentIndex(max(0, picker.findData(action.result_variable)))
            self.result_picker = picker
            self.form.addRow("Save result in", picker)
        for field, kind in BINDABLE.get(action.kind, {}).items():
            # Keep the inspector compact until a compatible variable exists.
            if (field not in action.bindings and
                    not any(item["type"] == kind
                            for item in self.variable_definitions)):
                continue
            picker = QComboBox()
            picker.addItem("Use direct value", "")
            for item in self.variable_definitions:
                if item["type"] == kind:
                    picker.addItem(item["name"], item["name"])
            selected = action.bindings.get(field, "")
            if selected and picker.findData(selected) < 0:
                picker.addItem(selected + " (unavailable)", selected)
            picker.setCurrentIndex(max(0, picker.findData(selected)))
            self.variable_controls[field] = picker
            self.form.addRow(f"Bind {field.replace('_', ' ')}", picker)
            picker.currentIndexChanged.connect(self._update_binding_visibility)
        self._update_binding_visibility()
        if action.kind in ("file_check", "file_wait", "file_copy",
                           "file_move", "folder_create"):
            if action.kind == "file_copy":
                message = ("Copies one regular file. Existing destinations "
                           "are protected unless Overwrite is checked.")
            elif action.kind == "file_move":
                message = ("Moves one regular file: the source is removed after "
                           "the destination is written. Overwrite replaces an "
                           "existing destination only when explicitly checked.")
            elif action.kind == "folder_create":
                message = ("Creates this folder and any missing parent folders. "
                           "Existing real folders are accepted.")
            elif action.kind == "file_wait":
                message = ("Waits until a regular file exists; 0-second timeout "
                           "checks once. Pause/Stop interrupt polling.")
            else:
                message = "Checks a file exists; otherwise the action fails."
            hint = QLabel(
                message + " Choose absolute local paths (no .. traversal). "
                "The workflow never invokes a shell or deletes directories.")
            hint.setWordWrap(True)
            hint.setObjectName("panelHint")
            self.form.addRow(hint)
        if action.kind == "wait_window":
            self.controls["window_wait_source"].currentTextChanged.connect(
                self.update_wait_window_visibility)
            self.update_wait_window_visibility()
            hint = QLabel(
                "Choose a visible window or enter its exact title to wait "
                "for one that is not open yet. Optional class filters "
                "duplicate titles. Workflow uses the target selected above "
                "the editor. Hidden means minimized/unmapped, only while "
                "the window manager still enumerates it. Closed means absent. "
                "No focus changes or keyboard input are sent.")
            hint.setWordWrap(True)
            hint.setObjectName("panelHint")
            self.form.addRow(hint)
        if action.kind == "click_image":
            hint = QLabel(
                "Offsets are physical pixels from the center of the matched "
                "reference image: positive X moves right, positive Y moves "
                "down. Negative offsets are allowed. Zero clicks the center. "
                "Preview checks the target without clicking.")
            hint.setWordWrap(True)
            hint.setObjectName("panelHint")
            self.form.addRow(hint)
            preview = QPushButton("Preview click point…")
            preview.clicked.connect(self._preview_image_click)
            self.form.addRow(preview)
        if action.kind == "launch":
            self.controls["launch_mode"].currentTextChanged.connect(
                self.update_launch_visibility)
            self.update_launch_visibility()
            info = QLabel(
                "Application runs an executable directly; each argument line "
                "is a literal parameter (no shell). File opens in the default "
                "desktop app; URL opens HTTP(S) in the default browser. "
                "Test launch actually opens the target.")
            info.setWordWrap(True)
            info.setObjectName("panelHint")
            self.form.addRow(info)
            test = QPushButton("Test launch…")
            test.setToolTip(
                "Actually start/open the selected app, file or URL using "
                "current form values; does not save the action.")
            test.clicked.connect(self._test_launch)
            self.form.addRow(test)
        if action.kind in ("clipboard_set", "clipboard_paste"):
            info = QLabel(
                "Clipboard text is saved as plaintext in macro files and local "
                "crash recovery, but is not shown in action labels or run logs. "
                + ("Empty text clears clipboard text."
                   if action.kind == "clipboard_set" else
                   "Blank text pastes the current clipboard. With custom text, "
                   "the previous text is restored if unchanged; non-text clipboard "
                   "cannot be restored."))
            info.setWordWrap(True)
            info.setObjectName("panelHint")
            self.form.addRow(info)
        if action.kind not in CONTROL:
            self.controls["failure_policy"].currentTextChanged.connect(
                self.update_failure_visibility)
            caution = QLabel(
                "Stop is safest. Skip continues after an error, even if a "
                "click or keystroke might already have taken effect. "
                "Retry is supported only for image/condition timeouts "
                "before input is sent.")
            caution.setWordWrap(True)
            caution.setObjectName("panelHint")
            self.form.addRow(caution)
            if action.kind not in ("click_image", "wait_until", "wait_text"):
                retry_option = self.controls["failure_policy"]
                retry_option.removeItem(retry_option.findText("retry"))
            self.update_failure_visibility()
        if action.kind in ("click", "move", "drag"):
            pick = QPushButton("Pick start (3 s)")
            pick.setToolTip("Move the pointer to the start position; capture after 3 seconds. "
                            "Set window visibility in View → During screen selection.")
            pick.clicked.connect(lambda: self.pick_coordinates.emit("start"))
            self.form.addRow(pick)
            test = QPushButton("Test position")
            test.setToolTip("Move the pointer to the selected X/Y coordinates.")
            test.clicked.connect(self._test_coordinates)
            self.form.addRow(test)
            if action.kind == "drag":
                destination = QPushButton("Pick destination (3 s)")
                destination.setToolTip("Move to the drag destination; capture after 3 seconds. "
                                   "Set window visibility in View → During screen selection.")
                destination.clicked.connect(lambda: self.pick_coordinates.emit("destination"))
                self.form.addRow(destination)
        if action.kind in ("find_text", "wait_text"):
            draw = QPushButton("Draw screen region…")
            draw.clicked.connect(self.pick_region.emit)
            self.form.addRow(draw)
            preview = QPushButton("Live OCR preview…")
            preview.setToolTip(
                "Read-only local OCR of the visible screen or configured region. "
                "No mouse clicks, saved images, or network services.")
            preview.clicked.connect(self._preview_text)
            self.form.addRow(preview)
            hint = QLabel(
                "Requires local Tesseract and the selected language pack. "
                "Uses exact words ignoring case (not fuzzy matching). "
                "Prefer a small region for accuracy and speed. "
                "A click is sent only after a recognized phrase exceeds "
                "the confidence threshold. Text and screenshots stay local.")
            hint.setWordWrap(True)
            hint.setObjectName("panelHint")
            self.form.addRow(hint)
        if action.kind == "watch_start":
            draw = QPushButton("Draw screen region…")
            draw.setToolTip("Drag a rectangle on your desktop; Esc cancels. "
                            "Set window visibility in View → During screen selection.")
            draw.clicked.connect(self.pick_region.emit)
            self.form.addRow(draw)
            tester = QPushButton("Test monitoring…")
            tester.setToolTip(
                "Preview the live screenshots and change detection without "
                "running any workflow actions. Uses the current form values.")
            tester.clicked.connect(self._test_monitoring)
            self.form.addRow(tester)
            info = QLabel("0 maximum changes = watch until Stop. "
                          "Live tests use current form values but never run "
                          "the nested actions or save workflow changes.")
            info.setWordWrap(True)
            info.setObjectName("panelHint")
            self.form.addRow(info)
        if action.kind in VISUAL:
            color = QPushButton("Sample pixel (3 s)")
            color.setToolTip("Capture the pixel beneath the pointer after 3 seconds. "
                             "Set window visibility in View → During screen selection.")
            color.clicked.connect(lambda: self.pick_coordinates.emit("pixel"))
            self.form.addRow(color)
        if "condition_source" in self.controls:
            self.controls["condition_source"].currentTextChanged.connect(
                self.update_visual_visibility
            )
            if action.kind == "click_image":
                self.controls["condition_source"].setCurrentText("image")
                self.controls["condition_source"].setEnabled(False)
                self.controls["match_mode"].setCurrentText("matches")
                self.controls["match_mode"].setEnabled(False)
            self.update_visual_visibility()

    def _update_binding_visibility(self, _=None):
        for field, picker in self.variable_controls.items():
            bound = bool(picker.currentData())
            names = (("x", "y") if field == "point" else
                     ("to_x", "to_y") if field == "to_point" else (field,))
            for name in names:
                widget = self.controls.get(name)
                if widget is not None:
                    widget.setEnabled(not bound)

    def _forget_wait_identity(self, _=None):
        self._wait_identity = (0, 0)

    def update_wait_window_visibility(self, _=None):
        mode = self.controls.get("window_wait_source")
        if mode is None:
            return
        custom = mode.currentText() == "custom"
        self.wait_pick.setEnabled(custom)
        for name in ("window_wait_title", "window_wait_class"):
            self.controls[name].setEnabled(custom)

    def pick_wait_window(self):
        if self.current is None or self.current.kind != "wait_window":
            return
        try:
            dialog = WindowPickerDialog(WindowManager(), self)
        except (WindowUnavailable, OSError) as exc:
            QMessageBox.warning(self, "Window picker unavailable", str(exc))
            return
        dialog.setWindowTitle("Choose window to observe")
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected is not None:
            window = dialog.selected
            self.controls["window_wait_title"].setText(window.title)
            self.controls["window_wait_class"].setText(window.class_name)
            self._wait_identity = (window.handle, window.pid)

    def update_launch_visibility(self, _=None):
        mode = self.controls.get("launch_mode")
        if mode is None:
            return
        is_app = mode.currentText() == "application"
        args = self.controls["launch_args"]
        args.setEnabled(is_app)
        self.launch_browse.setVisible(mode.currentText() != "url")

    def update_failure_visibility(self, _=None):
        policy = self.controls.get("failure_policy")
        if policy is None:
            return
        retry = policy.currentText() == "retry"
        for field in ("retry_count", "retry_delay"):
            widget = self.controls.get(field)
            if widget is not None:
                widget.setVisible(retry)
                label = self.form.labelForField(widget)
                if label is not None:
                    label.setVisible(retry)

    def update_visual_visibility(self, _=None):
        widget = self.controls.get("condition_source")
        if widget is None:
            return
        image = widget.currentText() == "image"
        for field in IMAGE_FIELDS:
            if field in self.controls:
                self.controls[field].setEnabled(image)
        for field in PIXEL_FIELDS:
            if field in self.controls:
                self.controls[field].setEnabled(not image)

    def update_picked_coordinates(self, kind, x, y, color=None):
        fields = {
            "start": ("x", "y"),
            "destination": ("to_x", "to_y"),
            "pixel": ("pixel_x", "pixel_y"),
        }.get(kind, ())
        if fields and all(field in self.controls for field in fields):
            self.controls[fields[0]].setText(str(x))
            self.controls[fields[1]].setText(str(y))
        if kind == "pixel" and color and "pixel_color" in self.controls:
            self.controls["pixel_color"].setText(color)

    def update_picked_region(self, x, y, width, height):
        for field, value in zip(("region_x", "region_y", "region_w", "region_h"),
                                (x, y, width, height)):
            if field in self.controls:
                self.controls[field].setText(str(value))

    def _test_coordinates(self):
        try:
            x = int(self.controls["x"].text())
            y = int(self.controls["y"].text())
        except (ValueError, KeyError):
            QMessageBox.warning(self, "Invalid coordinates", "Enter valid X/Y coordinates.")
            return
        self.test_move.emit(x, y)

    def browse_file_action(self, target, field):
        if self.current is None:
            return
        if self.current.kind == "folder_create":
            path = QFileDialog.getExistingDirectory(
                self, "Choose folder (edit the path to create a new folder)")
        elif field == "file_destination":
            path, _ = QFileDialog.getSaveFileName(
                self, "Choose destination file", "", "All files (*)")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose local source file", "", "All files (*)")
        if path:
            target.setText(path)

    def browse_launch(self, target):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose application or file", "",
            "All files (*)")
        if path:
            target.setText(path)

    def browse_image(self, target):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose cropped reference image", "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All files (*)")
        if path:
            target.setText(path)

    def _read_action(self):
        """Validate current form fields without saving or mutating the workflow."""
        data = asdict(self.current)
        for field, widget in self.controls.items():
            if isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QPlainTextEdit):
                value = widget.toPlainText()
                if data["kind"] == "clipboard_paste" and not value:
                    value = None
            else:
                value = convert(field, widget.text())
            data[field] = value
        data["bindings"] = {
            field: picker.currentData()
            for field, picker in self.variable_controls.items()
            if picker.currentData()
        }
        if self.result_picker is not None:
            data["result_variable"] = self.result_picker.currentData()
        if data["kind"] == "wait_window":
            data["window_wait_handle"], data["window_wait_pid"] = self._wait_identity
        if data["kind"] == "launch" and data["launch_mode"] != "application":
            data["launch_args"] = ""
        if data["kind"] == "click_image":
            data["condition_source"] = "image"
            data["match_mode"] = "matches"
        return validate_action(data)

    def _preview_image_click(self):
        if self.current is None or self.current.kind != "click_image":
            return
        try:
            action = self._read_action()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid image-click settings", str(exc))
            return
        self.preview_image_click.emit(action)

    def _preview_text(self):
        if self.current is None or self.current.kind not in ("find_text", "wait_text"):
            return
        try:
            action = self._read_action()
            if not action.text_target.strip():
                raise ValueError("Enter the phrase to recognize before previewing.")
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid OCR settings", str(exc))
            return
        self.preview_text.emit(action)

    def _test_launch(self):
        if self.current is None or self.current.kind != "launch":
            return
        try:
            action = self._read_action()
        except (TypeError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid launch settings", str(exc))
            return
        self.test_launch.emit(action)

    def _test_monitoring(self):
        if self.current is None or self.current.kind != "watch_start":
            return
        try:
            action = self._read_action()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid region monitor settings", str(exc))
            return
        self.test_monitoring.emit(action)

    def commit(self):
        if self.current is None:
            return
        try:
            action = self._read_action()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid action settings", str(exc))
            return
        self.apply_action.emit(action)
