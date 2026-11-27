from qt_test_helpers import close_test_window
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from PySide6.QtWidgets import QApplication
from macro_qt import MacroWindow
from macro_model import Action

app = QApplication.instance() or QApplication([])


class WindowTests(unittest.TestCase):
    def test_minimize_preference_persists_and_restores(self):
        from PySide6.QtCore import QSettings
        w = MacroWindow()
        try:
            w.minimize_on_run.setChecked(True)
            self.assertTrue(QSettings("MacroRunner", "Desktop").value(
                "minimize_on_run", False, type=bool))
            w.show()
            app.processEvents()
            w._restore_after_run = True
            w.showMinimized()
            app.processEvents()
            self.assertTrue(w.isMinimized())
            w._finished(True, "Done")
            app.processEvents()
            self.assertFalse(w.isMinimized())
            self.assertFalse(w._restore_after_run)
        finally:
            w.minimize_on_run.setChecked(False)
            close_test_window(w)

    def test_minimize_off_keeps_window_unchanged(self):
        w = MacroWindow()
        try:
            w.show()
            app.processEvents()
            w._restore_after_run = False
            w._finished(True, "Done")
            self.assertFalse(w.isMinimized())
        finally:
            close_test_window(w)


    def test_pending_completion_keeps_editor_locked(self):
        w = MacroWindow()
        try:
            from types import SimpleNamespace
            w.executor = SimpleNamespace(thread=SimpleNamespace(is_alive=lambda: False))
            self.assertTrue(w._busy())
            w.executor = None
            self.assertFalse(w._busy())
        finally:
            w.executor = None
            close_test_window(w)

    def test_window_undo_and_full_workflow(self):
        w = MacroWindow()
        try:
            w._replace_actions([Action(kind="wait", seconds=1)])
            w.tree.insert_kind("loop_start")
            self.assertEqual([a.kind for a in w.actions],
                             ["wait", "loop_start", "wait", "loop_end"])
            w.undo()
            self.assertEqual([a.kind for a in w.actions], ["wait"])
            w.redo()
            self.assertEqual(w.actions[-1].kind, "loop_end")
        finally:
            close_test_window(w)

    def test_scrollable_palette_and_inspector(self):
        w = MacroWindow()
        try:
            w.search.setText("click")
            visible = [w.palette.item(i).text() for i in range(w.palette.count())
                       if not w.palette.item(i).isHidden()]
            self.assertEqual(len(visible), 2)
            w._replace_actions([Action(kind="wait", seconds=1)])
            w.tree.topLevelItem(0).setSelected(True)
            self.assertEqual(w.inspector.current.kind, "wait")
        finally:
            close_test_window(w)


class ScreenSelectionVisibilityTests(unittest.TestCase):
    def setUp(self):
        guard = patch("macro_qt.require_legacy_desktop")
        guard.start()
        self.addCleanup(guard.stop)
        self.w = MacroWindow()
        self.original_mode = self.w.settings.value("selection_window_mode")
        self.w.show()
        app.processEvents()

    def tearDown(self):
        self.w._end_screen_selection()
        close_test_window(self.w)
        if self.original_mode is None:
            self.w.settings.remove("selection_window_mode")
        else:
            self.w.settings.setValue("selection_window_mode", self.original_mode)

    def test_menu_persists_all_three_modes(self):
        actions = self.w.selection_mode_menu.actions()
        self.assertEqual(len(actions), 3)
        for mode, action in zip(("show", "minimize", "hide"), actions):
            with self.subTest(mode=mode):
                action.trigger()
                self.assertTrue(action.isChecked())
                self.assertEqual(self.w.settings.value("selection_window_mode"), mode)
                self.assertEqual(self.w._selection_window_mode(), mode)

    def test_selection_visibility_modes_restore_editor(self):
        for mode in ("show", "minimize", "hide"):
            with self.subTest(mode=mode):
                self.w.settings.setValue("selection_window_mode", mode)
                self.assertTrue(self.w._begin_screen_selection())
                self.assertTrue(self.w._busy())
                self.assertFalse(self.w._begin_screen_selection())
                self.assertFalse(self.w.selection_mode_menu.isEnabled())
                if mode == "hide":
                    self.assertFalse(self.w.isVisible())
                elif mode == "minimize":
                    self.assertTrue(self.w.isMinimized())
                else:
                    self.assertTrue(self.w.isVisible())
                    self.assertFalse(self.w.isMinimized())
                self.w._end_screen_selection()
                app.processEvents()
                self.assertTrue(self.w.isVisible())
                self.assertFalse(self.w.isMinimized())
                self.assertFalse(self.w._busy())
                self.assertTrue(self.w.selection_mode_menu.isEnabled())

    def test_previously_minimized_window_is_not_restored(self):
        self.w.settings.setValue("selection_window_mode", "hide")
        self.w.showMinimized()
        app.processEvents()
        self.assertTrue(self.w._begin_screen_selection())
        self.w._end_screen_selection()
        self.assertTrue(self.w.isMinimized())

    def test_region_selection_restores_on_success_and_cancel(self):
        class FakePicker:
            def __init__(self, selected, cancelled):
                self.selected = selected
                self.cancelled = cancelled
                self.shown = False
            def show(self):
                self.shown = True
            def cancel(self, notify=True):
                if notify:
                    self.cancelled()

        self.w.inspector.show_action(Action(kind="watch_start", region_x=0,
                                            region_y=0, region_w=200, region_h=100))
        scheduled = []
        timer = SimpleNamespace(singleShot=lambda delay, fn: scheduled.append((delay, fn)))
        with patch("macro_qt.QTimer", timer), patch("macro_qt.RegionPicker", FakePicker):
            self.w.settings.setValue("selection_window_mode", "hide")
            self.w._pick_region()
            self.assertFalse(self.w.isVisible())
            self.assertEqual(scheduled[-1][0], 150)
            self.w._pick_region()  # Ignore overlapping pick requests.
            self.assertEqual(len(scheduled), 1)
            scheduled.pop()[1]()
            picker = self.w.region_picker
            self.assertTrue(picker.shown)
            picker.selected(12, 20, 80, 60)
            self.assertTrue(self.w.isVisible())
            self.assertIsNone(self.w.region_picker)
            self.assertEqual(self.w.inspector.controls["region_x"].text(), "12")
            self.assertEqual(self.w.inspector.controls["region_h"].text(), "60")

            self.w.settings.setValue("selection_window_mode", "minimize")
            self.w._pick_region()
            self.assertTrue(self.w.isMinimized())
            scheduled.pop()[1]()
            self.w.region_picker.cancel()
            self.assertTrue(self.w.isVisible())
            self.assertFalse(self.w.isMinimized())
            self.assertEqual(self.w.inspector.controls["region_x"].text(), "12")

    def test_point_and_pixel_pick_restore_even_on_failure(self):
        scheduled = []
        timer = SimpleNamespace(singleShot=lambda delay, fn: scheduled.append((delay, fn)))
        fake = SimpleNamespace(
            position=lambda: (55, 66),
            screenshot=lambda region: Image.new("RGB", (1, 1), (16, 32, 48)),
        )
        self.w.settings.setValue("selection_window_mode", "hide")
        with patch("macro_qt.QTimer", timer), patch("macro_qt.get_automation", return_value=fake):
            self.w.inspector.show_action(Action(kind="click", x=1, y=2))
            self.w._pick_coordinates("start")
            self.assertFalse(self.w.isVisible())
            self.assertEqual(scheduled[-1][0], 3000)
            scheduled.pop()[1]()
            self.assertTrue(self.w.isVisible())
            self.assertEqual(self.w.inspector.controls["x"].text(), "55")
            self.assertEqual(self.w.inspector.controls["y"].text(), "66")

            self.w.inspector.show_action(Action(kind="wait_until", condition_source="pixel"))
            self.w._pick_coordinates("pixel")
            scheduled.pop()[1]()
            self.assertTrue(self.w.isVisible())
            self.assertEqual(self.w.inspector.controls["pixel_color"].text(), "#102030")

        errors = []
        fake.position = lambda: (_ for _ in ()).throw(OSError("Capture denied"))
        with patch("macro_qt.QTimer", timer), patch("macro_qt.get_automation", return_value=fake):
            with patch("macro_qt.QMessageBox.warning", side_effect=lambda *args: errors.append(args)):
                self.w._pick_coordinates("pixel")
                self.assertFalse(self.w.isVisible())
                scheduled.pop()[1]()
                self.assertTrue(self.w.isVisible())
                self.assertIn("Capture denied", str(errors))

    def test_close_cancels_pending_region_picker(self):
        scheduled = []
        timer = SimpleNamespace(singleShot=lambda delay, fn: scheduled.append(fn))
        self.w.settings.setValue("selection_window_mode", "hide")
        with patch("macro_qt.QTimer", timer):
            self.w._pick_region()
            self.assertFalse(self.w.isVisible())
            close_test_window(self.w)
            scheduled.pop()()  # The queued callback must not open the overlay.
            self.assertIsNone(self.w.region_picker)
            self.assertFalse(self.w.isVisible())
