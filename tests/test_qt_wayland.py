"""Offscreen geometry and worker handoff tests; no native portal."""
import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from macro_platform import DesktopUnavailable
from macro_qt_wayland import WaylandRunGuard, single_screen, EditorWorker
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
                # A DPI notification alone is not a coordinate change.
                callback = screen.logicalDotsPerInchChanged.connect.call_args.args[0]
                callback(96.0)
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
    def test_worker_passes_stop_event_and_records_error(self):
        operation = Mock(side_effect=DesktopUnavailable("denied"))
        worker = EditorWorker(operation)
        worker.stop()
        worker.run()
        operation.assert_called_once_with(worker.stopped)
        self.assertTrue(worker.stopped.is_set())
        self.assertIsInstance(worker.error, DesktopUnavailable)
        self.assertIsNone(worker.result)

    def test_timed_pointer_pick_does_not_open_region_overlay(self):
        from macro_qt import MacroWindow
        from macro_model import Action
        from qt_test_helpers import close_test_window

        with patch.object(MacroWindow, "_start_hotkeys"):
            window = MacroWindow()
        try:
            window.show()
            window.inspector.show_action(Action(kind="click", x=1, y=2))
            guard = Mock()
            guard.pick_pointer.return_value = ((9, 7), (12, 34, 56))
            def operation(fn, *, announce=False):
                self.assertTrue(announce)
                self.assertTrue(window.isVisible())
                self.assertFalse(window.isMinimized())
                return fn(guard, threading.Event(), Mock())
            with patch("macro_qt.wayland_trial_enabled", return_value=True), patch(
                    "macro_qt.WaylandRegionPicker") as picker, patch.object(
                    window, "_wayland_editor_operation", side_effect=operation):
                window._pick_coordinates("start")
            picker.assert_not_called()
            self.assertEqual(window.inspector.controls["x"].text(), "9")
            self.assertEqual(window.inspector.controls["y"].text(), "7")
        finally:
            close_test_window(window)

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


class RegionLifecycleTests(unittest.TestCase):
    def test_region_selection_uses_one_unscaled_frame_and_restores_editor(self):
        from macro_qt import MacroWindow
        from qt_test_helpers import close_test_window

        with patch.object(MacroWindow, "_start_hotkeys"):
            window = MacroWindow()
        original_mode = window.settings.value("selection_window_mode")
        image = Image.new("RGB", (20, 20), "red")
        image.putpixel((2, 3), (0, 128, 0))
        rect = (2, 3, 8, 6)
        try:
            for mode in ("hide", "minimize", "show"):
                for choice in ("select", "cancel", "capture"):
                    with self.subTest(mode=mode, choice=choice):
                        window.showNormal()
                        app.processEvents()
                        window.settings.setValue("selection_window_mode", mode)
                        observations = []
                        guard = Mock()
                        guard.size = (20, 20)

                        class Picker:
                            def __init__(self, screen, size, frame, selected, cancelled):
                                self.selected, self.cancelled = selected, cancelled
                                observations.append(("frame", frame is image, size))
                                self.closed = False

                            def show(self):
                                observations.append(("overlay", window.isVisible(),
                                                     window.isMinimized(), window._busy()))
                                self.closed = True
                                if choice == "cancel":
                                    self.cancelled()
                                else:
                                    self.selected(*rect)

                            def cancel(self, notify=True):
                                self.closed = True
                                if notify:
                                    self.cancelled()

                            def reject(self):
                                self.cancel()

                        def capture(operation):
                            observations.append(("capture", window.isVisible(),
                                                 window.isMinimized(), window._busy()))
                            return image

                        with patch.object(window, "_require_wayland_editor"), patch(
                                "macro_qt.WaylandRunGuard", return_value=guard), patch.object(
                                window, "_wayland_worker_result", side_effect=capture) as grab, patch(
                                "macro_qt.WaylandRegionPicker", Picker):
                            result = window._wayland_select_region(capture=choice == "capture")

                        self.assertEqual(observations[0],
                                         ("capture", mode != "hide", mode == "minimize", True))
                        self.assertEqual(observations[1], ("frame", True, (20, 20)))
                        self.assertEqual(observations[2], ("overlay", True, False, True))
                        grab.assert_called_once()
                        if choice == "capture":
                            self.assertEqual(result.size, (8, 6))
                            self.assertEqual(result.getpixel((0, 0)), (0, 128, 0))
                        else:
                            self.assertEqual(result, rect if choice == "select" else None)
                        self.assertIsNone(window._wayland_picker)
                        self.assertTrue(window.isVisible())
                        self.assertFalse(window.isMinimized())
                        self.assertFalse(window._busy())
        finally:
            if original_mode is None:
                window.settings.remove("selection_window_mode")
            else:
                window.settings.setValue("selection_window_mode", original_mode)
            close_test_window(window)
