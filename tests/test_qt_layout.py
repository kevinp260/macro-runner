"""Regression coverage for three-panel sizing and custom field controls."""
import unittest

from PySide6.QtCore import Qt
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QFrame, QPushButton, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit,
    QSpinBox, QDoubleSpinBox, QComboBox
)

from macro_model import Action
from macro_qt import MacroWindow, field_controls_style
from macro_qt_properties import pad_spinbox_text
from macro_ui_assets import ICON_DIR

app = QApplication.instance() or QApplication([])


class EditorLayoutTests(unittest.TestCase):
    def test_minimum_widths_and_rounded_three_panel_gutters(self):
        window = MacroWindow()
        try:
            window.resize(1020, 680)
            window.show()
            app.processEvents()
            window.splitter.setSizes([1, 1, 1])
            app.processEvents()

            self.assertGreaterEqual(window.minimumWidth(), 1020)
            self.assertEqual(window.splitter.handleWidth(), 12)
            self.assertFalse(window.splitter.childrenCollapsible())
            for i in range(3):
                panel = window.splitter.widget(i)
                self.assertIsInstance(panel, QFrame)
                self.assertEqual(panel.objectName(), "panel")
                self.assertGreaterEqual(panel.width(), panel.minimumWidth())
            self.assertGreaterEqual(window.inspector.width(), 345)
            self.assertIn("QSplitter::handle", app.styleSheet())
        finally:
            window.close()

    def test_long_inspector_buttons_use_full_form_width(self):
        window = MacroWindow()
        try:
            window.show()
            window.inspector.show_action(Action(kind="drag", x=1, y=2, to_x=3, to_y=4))
            app.processEvents()

            panel = window.inspector
            self.assertEqual(panel.scroll.horizontalScrollBarPolicy(),
                             Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            for title in ("Pick start (3 s)", "Test position",
                          "Pick destination (3 s)"):
                matching = [
                    child for child in panel.content.findChildren(QPushButton)
                    if title in child.text()
                ]
                self.assertEqual(len(matching), 1)
                button = matching[0]
                row, role = panel.form.getWidgetPosition(button)
                self.assertGreaterEqual(row, 0)
                self.assertEqual(role, QFormLayout.ItemRole.SpanningRole)
                self.assertGreaterEqual(button.width(), button.sizeHint().width())
        finally:
            window.close()

    def test_labels_have_transparent_padding_and_consistent_panel_styles(self):
        from PySide6.QtWidgets import QLabel
        window = MacroWindow()
        try:
            window.show()
            app.processEvents()
            self.assertEqual(window.inspector.heading.objectName(), "panelHeading")
            self.assertEqual(window.inspector.hint.objectName(), "panelHint")
            self.assertEqual(window.counter.objectName(), "actionCount")
            headings = window.findChildren(QLabel, "panelHeading")
            self.assertGreaterEqual(len(headings), 3)  # Actions, Workflow, Properties

            for theme in ("dark", "light"):
                with self.subTest(theme=theme):
                    window.set_theme(theme)
                    stylesheet = app.styleSheet()
                    self.assertIn(
                        "QLabel { background: transparent; border: none; padding: 1px 3px; }",
                        stylesheet)
                    self.assertIn("QLabel#panelHint { padding: 2px 3px 6px 3px; }",
                                  stylesheet)
                    self.assertIn("QLabel#actionCount {", stylesheet)
                    self.assertIn("border-radius: 6px; padding: 3px 8px;",
                                  stylesheet)
                    window.inspector.show_action(Action(kind="click", x=1, y=2))
                    app.processEvents()
                    self.assertTrue(window.inspector.hint.text())
        finally:
            window.close()

    def test_disabled_action_count_and_undo_redo(self):
        window = MacroWindow()
        try:
            window._replace_actions([Action(kind="wait", seconds=1),
                                     Action(kind="click", x=3, y=4)])
            self.assertNotIn("disabled", window.counter.text())
            first = window.tree.topLevelItem(0)
            first.setCheckState(0, Qt.CheckState.Unchecked)
            self.assertFalse(window.actions[0].enabled)
            self.assertIn("1 disabled", window.counter.text())
            self.assertTrue(window.history.can_undo)
            window.undo()
            self.assertTrue(window.actions[0].enabled)
            self.assertEqual(window.tree.topLevelItem(0).checkState(0),
                             Qt.CheckState.Checked)
            window.redo()
            self.assertFalse(window.actions[0].enabled)
            self.assertEqual(window.tree.topLevelItem(0).checkState(0),
                             Qt.CheckState.Unchecked)
        finally:
            window.close()

    def test_numeric_editor_margins_on_main_window_and_inspector(self):
        window = MacroWindow()
        try:
            window.inspector.show_action(Action(kind="click", x=5, y=9))
            for widget in (window.repeats, window.delay,
                           window.inspector.controls["repeats"]):
                editor = widget.findChild(QLineEdit)
                self.assertIsNotNone(editor)
                self.assertEqual(editor.textMargins().left(), 11)
            # Explicit margin is on the internal editor, not a QSS string.
            standalone = QSpinBox()
            pad_spinbox_text(standalone)
            self.assertEqual(
                standalone.findChild(QLineEdit).textMargins().left(), 11)
            self.assertEqual(window.repeats.value(), 1)
            self.assertEqual(window.delay.value(), 3.0)
        finally:
            window.close()

    def test_numeric_editor_text_insets(self):
        window = MacroWindow()
        try:
            window.inspector.show_action(Action(kind="click", x=1, y=2))
            for widget in (window.repeats, window.delay,
                           window.inspector.controls["repeats"]):
                editor = widget.findChild(QLineEdit)
                self.assertIsNotNone(editor)
                self.assertEqual(editor.textMargins().left(), 11)
            self.assertIsInstance(window.repeats, QSpinBox)
            self.assertIsInstance(window.delay, QDoubleSpinBox)
            self.assertIsInstance(window.inspector.controls["button"], QComboBox)
        finally:
            window.close()

    def test_both_theme_arrow_resources_and_styles(self):
        window = MacroWindow()
        try:
            for theme in ("dark", "light"):
                with self.subTest(theme=theme):
                    window.set_theme(theme)
                    stylesheet = app.styleSheet()
                    self.assertIn("QSpinBox::up-arrow", stylesheet)
                    self.assertIn("QDoubleSpinBox::down-arrow", stylesheet)
                    self.assertIn("QComboBox::down-arrow", stylesheet)
                    self.assertIn("QLineEdit { padding-left: 10px; }", stylesheet)
                    self.assertIn(
                        "QComboBox { padding: 7px 29px 7px 11px; }", stylesheet)
                    self.assertIn(
                        "QSpinBox, QDoubleSpinBox { padding: 7px 29px 7px 0px; }",
                        stylesheet)
                    self.assertIn("QSpinBox > QLineEdit", stylesheet)
                    for direction in ("up", "down"):
                        path = ICON_DIR / f"chevron-{direction}-{theme}.svg"
                        self.assertTrue(path.is_file())
                        self.assertTrue(QSvgRenderer(str(path)).isValid())
                        self.assertIn(path.as_posix(), stylesheet)
                    self.assertEqual(field_controls_style(theme).count("image: url("), 3)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
