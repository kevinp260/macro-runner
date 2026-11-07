"""Scrollable, schema-driven Qt action inspector."""
from dataclasses import asdict

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QPushButton, QLabel, QFileDialog, QHBoxLayout,
    QMessageBox, QFrame, QPlainTextEdit
)

from macro_model import Action, validate_action
from macro_flow import CONTROL

# Describes only fields that are relevant to an action kind.
SPECS = {
    "click": ["x", "y", "button", "clicks", "interval"],
    "click_image": ["button", "timeout", "poll_interval"],
    "wait": ["seconds"],
    "wait_until": ["timeout", "poll_interval"],
    "key": ["key_mode", "keys"],
    "key_down": ["keys"],
    "key_up": ["keys"],
    "move": ["x", "y", "move_duration"],
    "scroll": ["scroll_amount"],
    "drag": ["x", "y", "to_x", "to_y", "move_duration", "button"],
    "clipboard_set": ["clipboard_text"],
    "clipboard_paste": ["clipboard_text", "clipboard_restore"],
    "launch": ["launch_mode", "launch_target", "launch_args"],
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
}
INTEGER = frozenset(("x", "y", "to_x", "to_y", "clicks", "scroll_amount",
                     "pixel_x", "pixel_y", "pixel_tolerance",
                     "region_x", "region_y", "region_w", "region_h",
                     "watch_pixel_tolerance", "watch_confirmations",
                     "watch_max_changes", "retry_count"))
FLOAT = frozenset(("interval", "seconds", "move_duration", "timeout",
                   "poll_interval", "confidence", "watch_change_percent",
                   "retry_delay"))
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
        if kind in ("click_image", "wait_until"):
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
    test_launch = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        # The inspector needs room for both labels and inputs (plus browse).
        self.setMinimumWidth(345)
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

    def show_action(self, action):
        self.current = action
        self._reset_form()
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
            if action.kind not in ("click_image", "wait_until"):
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
        if data["kind"] == "launch" and data["launch_mode"] != "application":
            data["launch_args"] = ""
        if data["kind"] == "click_image":
            data["condition_source"] = "image"
            data["match_mode"] = "matches"
        return validate_action(data)

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
