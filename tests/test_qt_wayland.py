"""Offscreen geometry and worker handoff tests; no native portal."""
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from macro_platform import DesktopUnavailable
from macro_qt_wayland import (WaylandRunGuard, single_screen, image_point,
                              selection_region, EditorWorker, SnapshotPicker)
from PIL import Image

app = QApplication.instance() or QApplication([])


def fake_screen(rect=QRect(0, 0, 1920, 1080), scale=1):
    return SimpleNamespace(geometry=lambda: rect, devicePixelRatio=lambda: scale,
                           geometryChanged=Mock(), logicalDotsPerInchChanged=Mock(),
                           physicalDotsPerInchChanged=Mock())


def fake_app(screens, platform="wayland"):
    return SimpleNamespace(platformName=lambda: platform, screens=lambda: screens,
                           screenAdded=Mock(), screenRemoved=Mock())


class WaylandGeometryTests(unittest.TestCase):
    def test_native_single_origin_screen(self):
        screen = fake_screen()
        with patch("macro_qt_wayland.QApplication.instance", return_value=fake_app([screen])):
            self.assertEqual(single_screen(), (screen, (1920, 1080)))

    def test_unsupported_display_layouts(self):
        for instance in (fake_app([fake_screen()], "xcb"), fake_app([]),
                         fake_app([fake_screen(), fake_screen()]),
                         fake_app([fake_screen(scale=1.25)]),
                         fake_app([fake_screen(QRect(100, 0, 1920, 1080))])):
            with self.subTest(instance=instance), patch(
                    "macro_qt_wayland.QApplication.instance", return_value=instance):
                with self.assertRaises(DesktopUnavailable):
                    single_screen()

    def test_guard_invalidates_and_factory_uses_snapshot(self):
        screen = fake_screen()
        instance = fake_app([screen])
        with patch("macro_qt_wayland.QApplication.instance", return_value=instance), patch(
                "macro_qt_wayland.QTimer") as timer:
            guard = WaylandRunGuard(None)
            try:
                self.assertFalse(guard.invalidated.is_set())
                screen.geometry = lambda: QRect(0, 0, 1600, 900)
                guard._check()
                self.assertTrue(guard.invalidated.is_set())
                with patch("macro_qt_wayland.WaylandAutomation") as adapter:
                    gate = object()
                    self.assertIs(guard.factory(gate), adapter.return_value)
                    adapter.assert_called_once_with(gate, (1920, 1080), guard.invalidated)
            finally:
                guard.close()
            timer.return_value.stop.assert_called_once()
            instance.screenAdded.disconnect.assert_called_once()


class EditorTests(unittest.TestCase):
    def test_scaled_snapshot_point_mapping(self):
        rect = QRect(10, 20, 960, 540)
        self.assertEqual(image_point(rect, (1920, 1080), 10, 20), (0, 0))
        self.assertEqual(image_point(rect, (1920, 1080), 490, 290), (960, 540))
        self.assertEqual(image_point(rect, (1920, 1080), 969, 559), (1918, 1078))
        self.assertIsNone(image_point(rect, (1920, 1080), 970, 560))
        self.assertIsNone(image_point(rect, (1920, 1080), 9, 20))
        self.assertIsNone(image_point(QRect(), (1920, 1080), 0, 0))

    def test_region_reverse_drag_includes_endpoint(self):
        self.assertEqual(selection_region((9, 6), (4, 2)), (4, 2, 6, 5))
        self.assertEqual(selection_region((0, 0), (0, 0)), (0, 0, 1, 1))

    def test_snapshot_cancel_and_accept(self):
        dialog = SnapshotPicker(Image.new("RGB", (20, 10)), point_mode=True)
        try:
            dialog.reject()
            self.assertIsNone(dialog.selection)
            dialog._selected((2, 3))
            self.assertEqual(dialog.selection, (2, 3))
        finally:
            dialog.deleteLater()

    def test_worker_passes_stop_event_and_records_error(self):
        operation = Mock(side_effect=DesktopUnavailable("denied"))
        worker = EditorWorker(operation)
        worker.stop()
        worker.run()
        operation.assert_called_once_with(worker.stopped)
        self.assertTrue(worker.stopped.is_set())
        self.assertIsInstance(worker.error, DesktopUnavailable)
        self.assertIsNone(worker.result)

    def test_read_only_capture_and_pointer_test_scope(self):
        # Exercise the context factories without Qt screen queries on worker.
        guard = Mock(spec=WaylandRunGuard)
        guard.size = (20, 10)
        stopped = threading.Event()
        session = Mock()
        capture = Mock()
        session.logical_size = guard.size
        session_cm = Mock()
        session_cm.__enter__ = Mock(return_value=session)
        session_cm.__exit__ = Mock(return_value=False)
        capture_cm = Mock()
        capture_cm.__enter__ = Mock(return_value=capture)
        capture_cm.__exit__ = Mock(return_value=False)
        guard._capture_session = lambda stop, devices: WaylandRunGuard._capture_session(
            guard, stop, devices=devices)
        with patch("macro_qt_wayland.WaylandSession", return_value=session_cm) as sessions, patch(
                "macro_qt_wayland.WaylandCapture", return_value=capture_cm):
            with WaylandRunGuard.capture_factory(guard, stopped) as screenshot:
                self.assertIs(screenshot, capture.screenshot)
            self.assertEqual(sessions.call_args.kwargs["devices"], 0)
            session.move_absolute.assert_not_called()
            WaylandRunGuard.test_move(guard, stopped, 2, 3)
            self.assertEqual(sessions.call_args.kwargs["devices"], 2)
            capture.screenshot.assert_called_once()
            session.move_absolute.assert_called_once_with(2, 3)
            self.assertEqual(session_cm.__exit__.call_count, 2)
            self.assertEqual(capture_cm.__exit__.call_count, 2)
