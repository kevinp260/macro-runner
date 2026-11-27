"""Offscreen geometry and worker handoff tests; no native portal."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from macro_platform import DesktopUnavailable
from macro_qt_wayland import WaylandRunGuard, single_screen

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
