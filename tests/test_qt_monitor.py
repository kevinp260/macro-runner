from qt_test_helpers import close_test_window
"""Read-only region monitor unit/UI tests with synthetic screenshots."""
import time
import unittest
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from macro_model import Action
from macro_qt import MacroWindow
from macro_qt_monitor import (RegionMonitorDialog, RegionMonitorWorker,
                              capture_error_text)
from macro_qt_properties import PropertiesPanel

app = QApplication.instance() or QApplication([])


def action():
    return Action(kind="watch_start", region_x=10, region_y=20,
                  region_w=10, region_h=10, poll_interval=0.1,
                  watch_change_percent=5.0, watch_pixel_tolerance=10,
                  watch_confirmations=2)


def pump_until(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class RegionMonitorTests(unittest.TestCase):
    def test_worker_reports_two_changes_and_no_duplicate_trigger(self):
        frames = [0, 255, 255, 255, 0, 0]
        captures = []

        def screenshot(region=None):
            captures.append(region)
            value = frames[min(len(captures) - 1, len(frames) - 1)]
            return Image.new("RGB", (10, 10), (value,) * 3)

        worker = RegionMonitorWorker(action(), screenshot=screenshot)
        observed = []
        errors = []
        worker.frame.connect(observed.append)
        worker.capture_error.connect(errors.append)
        try:
            worker.start()
            self.assertTrue(pump_until(
                lambda: any(f["triggers"] == 2 for f in observed), 3.0))
            self.assertFalse(errors)
            self.assertEqual([f["state"] for f in observed if f["state"] == "triggered"],
                             ["triggered", "triggered"])
            self.assertEqual(observed[0]["state"], "baseline")
            self.assertEqual(observed[0]["percent"], 0)
            self.assertEqual(observed[1]["state"], "confirming")
            self.assertEqual(observed[1]["confirmations"], 1)
            self.assertEqual(observed[2]["state"], "triggered")
            self.assertEqual(observed[2]["percent"], 100.0)
            self.assertEqual(observed[3]["state"], "below")
            self.assertEqual(observed[3]["percent"], 0.0)
            self.assertEqual(observed[-1]["triggers"], 2)
            self.assertEqual(observed[2]["mask"].getpixel((0, 0)),
                             (255, 255, 255))
            self.assertTrue(all(r == (10, 20, 10, 10) for r in captures))
        finally:
            worker.stop()
            self.assertTrue(worker.wait(2000))
            app.processEvents()
        self.assertIsNone(worker.detector)  # No retained screenshots after Stop.

    def test_reset_baseline_without_executing_macro(self):
        captures = []

        def screenshot(region=None):
            captures.append(region)
            return Image.new("RGB", (10, 10), (255, 255, 255))

        worker = RegionMonitorWorker(action(), screenshot=screenshot)
        observed = []
        worker.frame.connect(observed.append)
        try:
            worker.start()
            self.assertTrue(pump_until(
                lambda: len(observed) >= 2))
            self.assertEqual(observed[-1]["percent"], 0.0)
            worker.reset_baseline()
            self.assertTrue(pump_until(
                lambda: any(f["state"] == "reset" for f in observed)))
            self.assertEqual(observed[-1]["triggers"], 0)
            self.assertEqual(observed[-1]["confirmations"], 0)
            self.assertTrue(pump_until(lambda: len(observed) >= 4))
            self.assertTrue(all(f["triggers"] == 0 for f in observed))
        finally:
            worker.stop()
            self.assertTrue(worker.wait(2000))

    def test_capture_errors_are_actionable(self):
        def denied(region=None):
            raise PermissionError("screenshot access denied")

        worker = RegionMonitorWorker(action(), screenshot=denied)
        errors = []
        worker.capture_error.connect(errors.append)
        worker.start()
        try:
            self.assertTrue(pump_until(lambda: len(errors) == 1))
            self.assertIn("screenshot access denied", errors[0])
            self.assertIn("Screen capture failed", errors[0])
        finally:
            worker.stop()
            self.assertTrue(worker.wait(2000))
        self.assertIn("screen", capture_error_text(OSError("No display")).lower())

    def test_dialog_displays_preview_and_detection_metrics(self):
        dialog = RegionMonitorDialog(action(), screenshot=lambda region=None: None)
        try:
            dialog.show()
            dialog.position_away_from_region()
            before = Image.new("RGB", (10, 10), "black")
            now = Image.new("RGB", (10, 10), "white")
            dialog._frame_received({
                "state": "triggered", "baseline": before, "current": now,
                "mask": now, "percent": 100.0, "confirmations": 2, "triggers": 1,
            })
            self.assertIn("100.00%", dialog.percent_text.text())
            self.assertIn("2 / 2", dialog.progress_text.text())
            self.assertIn("1", dialog.trigger_text.text())
            self.assertIn("accepted", dialog.status.text())
            self.assertTrue(all(label.pixmap() is not None
                                for label in dialog.previews.values()))
            self.assertIn("5%", dialog.settings_text.text())
        finally:
            dialog.close()

    def test_inspector_uses_unapplied_form_values_and_rejects_invalid(self):
        panel = PropertiesPanel()
        selected = []
        warnings = []
        panel.test_monitoring.connect(selected.append)
        try:
            original = action()
            panel.show_action(original)
            button = next(w for w in panel.findChildren(QPushButton)
                          if w.text() == "Test monitoring…")
            panel.controls["region_x"].setText("42")
            panel.controls["watch_change_percent"].setText("2.5")
            button.click()
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0].region_x, 42)
            self.assertEqual(selected[0].watch_change_percent, 2.5)
            self.assertEqual(original.region_x, 10)  # No edit committed.
            panel.controls["region_w"].setText("0")
            with patch.object(QMessageBox, "warning",
                              side_effect=lambda *args: warnings.append(args)):
                button.click()
            self.assertEqual(len(selected), 1)
            self.assertEqual(len(warnings), 1)
        finally:
            panel.close()

    def test_main_window_minimizes_and_restores_on_monitor_close(self):
        class FakeDialog(QDialog):
            def __init__(self, a):
                super().__init__(None)
                self.action = a
                self.started = False
            def position_away_from_region(self): pass
            def start_monitoring(self): self.started = True
            def stop_monitoring(self): pass

        window = MacroWindow()
        old = window.settings.value("minimize_on_run")
        window.show()
        app.processEvents()
        try:
            window.minimize_on_run.setChecked(True)
            window.inspector.show_action(action())
            scheduled = []
            with patch("macro_qt.RegionMonitorDialog", FakeDialog), \
                    patch("macro_qt.QTimer.singleShot",
                          side_effect=lambda ms, fn: scheduled.append(fn)):
                window.inspector._test_monitoring()
                dialog = window.region_monitor
                self.assertIsNotNone(dialog)
                self.assertTrue(window._busy())
                self.assertFalse(window.toolbar_actions["run"].isEnabled())
                self.assertTrue(window.isMinimized())
                self.assertEqual(dialog.action.kind, "watch_start")
                scheduled[0]()
                self.assertTrue(dialog.started)
                dialog.done(0)
                app.processEvents()
                self.assertIsNone(window.region_monitor)
                self.assertFalse(window.isMinimized())
                self.assertFalse(window._busy())
        finally:
            if old is None:
                window.settings.remove("minimize_on_run")
            else:
                window.settings.setValue("minimize_on_run", old)
            close_test_window(window)


if __name__ == "__main__":
    unittest.main()
