"""Offscreen Variables editor, inspector bindings, undo/redo and recovery."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtCore import QCoreApplication, QEvent

from macro_model import Action, parse_document, serialize_document
from macro_qt import MacroWindow
from macro_qt_variables import VariablesDialog
from macro_recovery import RecoveryStore
from qt_test_helpers import close_test_window


app = QApplication.instance() or QApplication([])


def defn(name, kind, default):
    return {"name":name, "type":kind, "default":default}


class VariableQtTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.win = MacroWindow()
        self.win.recovery_store = RecoveryStore(self.root / "recovery.json")
        self.dialogs = []

    def make_dialog(self, *args, **kwargs):
        dialog = VariablesDialog(*args, **kwargs)
        self.dialogs.append(dialog)
        return dialog

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        close_test_window(self.win)
        self.win.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_dialog_validates_typed_defaults_and_session_overrides(self):
        dialog = self.make_dialog([])
        dialog.add_row()
        dialog.table.item(0, 0).setText("Clicks")
        dialog.table.cellWidget(0, 1).setCurrentText("number")
        dialog.table.item(0, 2).setText("4")
        dialog.table.item(0, 4).setText("9")
        dialog.table.cellWidget(0, 5).setChecked(True)
        dialog._accept()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.definitions, [defn("Clicks", "number", 4.0)])
        self.assertEqual(dialog.overrides, {"Clicks":9.0})

    def test_dialog_preserves_unset_outputs_and_coordinates(self):
        definitions = [
            defn("center", "coordinates", None),
            defn("label", "text", ""),
            defn("enabled", "boolean", True)]
        dialog = self.make_dialog(definitions, {"label":"private"})
        self.assertTrue(dialog.table.cellWidget(0,3).isChecked())
        self.assertTrue(dialog.table.cellWidget(1,5).isChecked())
        dialog._accept()
        self.assertEqual(dialog.definitions, definitions)
        self.assertEqual(dialog.overrides, {"label":"private"})

    def test_dialog_refuses_bad_type_without_accepting(self):
        dialog = self.make_dialog([defn("test","boolean",False)])
        dialog.table.item(0, 2).setText("not a bool")
        with patch("macro_qt_variables.QMessageBox.warning") as warning:
            dialog._accept()
        warning.assert_called_once()
        self.assertIsNone(dialog.definitions)

    def _set_variables(self, defs, overrides=None):
        with patch("macro_qt.VariablesDialog") as dialog:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.definitions = defs
            dialog.return_value.overrides = overrides or {}
            self.win.edit_variables()

    def test_variable_definitions_are_dirty_undoable_and_redoable(self):
        self.win._replace_actions([Action(kind="wait")])
        self.win._mark_clean()
        defs = [defn("delay","number",2)]
        self._set_variables(defs)
        self.assertEqual(self.win.variables, defs)
        self.assertTrue(self.win._is_dirty())
        self.win.undo()
        self.assertEqual(self.win.variables, [])
        self.win.redo()
        self.assertEqual(self.win.variables, defs)
        self.win._mark_clean()
        self._set_variables(defs, {"delay":8})
        self.assertFalse(self.win._is_dirty())
        self.assertEqual(self.win.variable_overrides, {"delay":8})

    def test_cannot_delete_variable_still_bound_to_action(self):
        defs = [defn("here","coordinates",[5,6])]
        self.win.variables = defs
        self.win._replace_actions([
            Action(kind="click", x=0, y=0, bindings={"point":"here"})])
        with patch("macro_qt.VariablesDialog") as dialog, patch(
                "macro_qt.QMessageBox.warning") as warning:
            dialog.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog.return_value.definitions = []
            dialog.return_value.overrides = {}
            self.win.edit_variables()
        warning.assert_called_once()
        self.assertEqual(self.win.variables, defs)

    def test_inspector_lists_compatible_variables_and_persists_binding(self):
        self.win.variables = [defn("point", "coordinates", [7,8]),
                              defn("title", "text", "hello")]
        self.win._replace_actions([Action(kind="click",x=0,y=0)])
        self.win.tree.topLevelItem(0).setSelected(True)
        panel = self.win.inspector
        combo = panel.variable_controls["point"]
        self.assertEqual(combo.findData("title"), -1)
        combo.setCurrentIndex(combo.findData("point"))
        self.assertFalse(panel.controls["x"].isEnabled())
        self.assertFalse(panel.controls["y"].isEnabled())
        panel.commit()
        self.assertEqual(self.win.actions[0].bindings, {"point":"point"})
        self.assertTrue(self.win._is_dirty())

    def test_image_match_and_clipboard_output_pickers(self):
        self.win.variables = [defn("position", "coordinates", None),
                              defn("clip", "text", None)]
        self.win._replace_actions([
            Action(kind="click_image", image_path="reference.png"),
            Action(kind="clipboard_read")])
        first = self.win.tree.topLevelItem(0)
        first.setSelected(True)
        panel = self.win.inspector
        picker = panel.result_picker
        self.assertEqual(picker.findData("clip"), -1)
        picker.setCurrentIndex(picker.findData("position"))
        panel.commit()
        self.assertEqual(self.win.actions[0].result_variable,"position")
        self.win.tree.clearSelection()
        second = self.win.tree.topLevelItem(1)
        second.setSelected(True)
        picker = self.win.inspector.result_picker
        self.assertEqual(picker.findData("position"), -1)
        picker.setCurrentIndex(picker.findData("clip"))
        self.win.inspector.commit()
        self.assertEqual(self.win.actions[1].result_variable,"clip")

    def test_document_save_open_legacy_and_crash_recovery(self):
        defs = [defn("label","text","Default")]
        self.win.variables = defs
        self.win._replace_actions([Action(
            kind="clipboard_set",clipboard_text="",
            bindings={"clipboard_text":"label"})])
        self.win.variable_overrides = {"label":"Run-only secret"}
        path = self.root / "workflow.json"
        self.win.current_file = str(path)
        self.assertTrue(self.win.save_workflow())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["settings"]["variables"], defs)
        self.assertNotIn("Run-only secret", str(data))
        self.assertFalse(self.win._is_dirty())
        self.win._replace_actions([
            Action(kind="clipboard_set", clipboard_text="changed")])
        self.win.recovery_store.write(
            self.win.actions, self.win.repeats.value(), self.win.delay.value(),
            variables=self.win.variables)
        snapshot = self.win.recovery_store.read()
        self.assertEqual(snapshot.variables, defs)
        with patch("macro_qt.QFileDialog.getOpenFileName",
                   return_value=(str(path),"")), patch(
                   "macro_qt.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.win.open_workflow()
        self.assertEqual(self.win.variables, defs)
        self.assertEqual(self.win.variable_overrides, {})
        self.assertEqual(self.win.actions[0].bindings,
                         {"clipboard_text":"label"})

    def test_new_workflow_clears_variables_and_overrides(self):
        self._set_variables([defn("label","text","text")],
                            {"label":"override"})
        self.win._mark_clean()
        self.win.new_workflow()
        self.assertEqual(self.win.variables, [])
        self.assertEqual(self.win.variable_overrides, {})


if __name__ == "__main__":
    unittest.main()
