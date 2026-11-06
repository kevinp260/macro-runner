"""Scrollable, schema-driven Qt action inspector."""
from dataclasses import asdict

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QPushButton, QLabel, QFileDialog, QHBoxLayout,
    QMessageBox, QFrame
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
    "loop_start": [],
    "if_start": [],
    "until_start": [],
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
}
INTEGER = frozenset(("x", "y", "to_x", "to_y", "clicks", "scroll_amount",
                     "pixel_x", "pixel_y", "pixel_tolerance",
                     "region_x", "region_y", "region_w", "region_h"))
FLOAT = frozenset(("interval", "seconds", "move_duration", "timeout",
                   "poll_interval", "confidence"))
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


def fields_for_kind(kind):
    fields = SPECS.get(kind, [])
    if kind in VISUAL:
        fields = fields + VISUAL_FIELDS
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
            self.controls["repeats"] = repeats
            self.form.addRow("Repeat count", repeats)
        if action.kind not in CONTROL:
            enabled = QCheckBox("Enabled")
            enabled.setChecked(action.enabled)
            self.controls["enabled"] = enabled
            self.form.addRow("", enabled)
        for field in fields_for_kind(action.kind):
            value = getattr(action, field)
            if field in COMBOS:
                widget = QComboBox()
                widget.addItems(COMBOS[field])
                widget.setCurrentText(str(value))
            else:
                widget = QLineEdit("" if value is None else str(value))
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
        if action.kind in ("click", "move", "drag"):
            pick = QPushButton("Pick start (3 s)")
            pick.setToolTip("Move the pointer to the start position; capture after 3 seconds.")
            pick.clicked.connect(lambda: self.pick_coordinates.emit("start"))
            self.form.addRow(pick)
            test = QPushButton("Test position")
            test.setToolTip("Move the pointer to the selected X/Y coordinates.")
            test.clicked.connect(self._test_coordinates)
            self.form.addRow(test)
            if action.kind == "drag":
                destination = QPushButton("Pick destination (3 s)")
                destination.setToolTip("Move to the drag destination; capture after 3 seconds.")
                destination.clicked.connect(lambda: self.pick_coordinates.emit("destination"))
                self.form.addRow(destination)
        if action.kind in VISUAL:
            color = QPushButton("Sample pixel (3 s)")
            color.setToolTip("Capture the pixel beneath the pointer after 3 seconds.")
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

    def _test_coordinates(self):
        try:
            x = int(self.controls["x"].text())
            y = int(self.controls["y"].text())
        except (ValueError, KeyError):
            QMessageBox.warning(self, "Invalid coordinates", "Enter valid X/Y coordinates.")
            return
        self.test_move.emit(x, y)

    def browse_image(self, target):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose cropped reference image", "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All files (*)")
        if path:
            target.setText(path)

    def commit(self):
        if self.current is None:
            return
        try:
            data = asdict(self.current)
            for field, widget in self.controls.items():
                if isinstance(widget, QSpinBox):
                    value = widget.value()
                elif isinstance(widget, QCheckBox):
                    value = widget.isChecked()
                elif isinstance(widget, QComboBox):
                    value = widget.currentText()
                else:
                    value = convert(field, widget.text())
                data[field] = value
            if data["kind"] == "click_image":
                data["condition_source"] = "image"
                data["match_mode"] = "matches"
            action = validate_action(data)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid action settings", str(exc))
            return
        self.apply_action.emit(action)
