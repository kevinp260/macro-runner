"""Desktop selection and legacy adapter tests without native dependencies."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from macro_platform import (DesktopUnavailable, desktop_platform, get_automation,
                            create_hotkeys, create_mouse_listener,
                            create_keyboard_listener)


class PlatformTests(unittest.TestCase):
    def test_session_detection(self):
        for platform, env, expected in (
            ("win32", {"XDG_SESSION_TYPE": "wayland"}, "windows"),
            ("linux", {"DISPLAY": ":0"}, "x11"),
            ("linux", {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, "x11"),
            ("linux", {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}, "wayland"),
            ("linux", {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}, "wayland"),
            ("linux", {"XDG_SESSION_TYPE": "wayland"}, "wayland"),
            ("linux", {"XDG_SESSION_TYPE": "x11"}, "unavailable"),
            ("linux", {}, "unavailable"),
            ("darwin", {}, "unsupported"),
        ):
            with self.subTest(platform=platform, env=env):
                self.assertEqual(desktop_platform(platform, env), expected)

    def test_unsupported_sessions_do_not_import_native_libraries(self):
        operations = (get_automation, lambda: create_hotkeys({}),
                      create_mouse_listener, create_keyboard_listener)
        for platform, message in (("wayland", "Wayland"),
                                  ("unavailable", "X11 display"),
                                  ("unsupported", "Windows")):
            for operation in operations:
                with self.subTest(platform=platform, operation=operation), patch(
                        "macro_platform.desktop_platform", return_value=platform), patch(
                        "builtins.__import__", side_effect=AssertionError("unexpected import")):
                    with self.assertRaisesRegex(DesktopUnavailable, message):
                        operation()

    def test_legacy_factories_preserve_contract(self):
        automation = Mock()
        mouse = Mock()
        keyboard = Mock()
        modules = {"pyautogui": automation,
                   "pynput": SimpleNamespace(mouse=mouse, keyboard=keyboard)}
        bindings = {"shortcut": Mock()}
        callbacks = {"on_press": Mock(), "on_release": Mock()}
        for platform in ("windows", "x11"):
            with self.subTest(platform=platform), patch.dict(sys.modules, modules), patch(
                    "macro_platform.desktop_platform", return_value=platform):
                self.assertIs(get_automation(), automation)
                self.assertIs(create_hotkeys(bindings), keyboard.GlobalHotKeys.return_value)
                self.assertIs(create_mouse_listener(on_click=bindings["shortcut"]),
                              mouse.Listener.return_value)
                self.assertIs(create_keyboard_listener(**callbacks), keyboard.Listener.return_value)
                keyboard.GlobalHotKeys.assert_called_with(bindings)
                mouse.Listener.assert_called_with(on_click=bindings["shortcut"])
                keyboard.Listener.assert_called_with(**callbacks)
                keyboard.GlobalHotKeys.return_value.start.assert_not_called()
                mouse.Listener.return_value.start.assert_not_called()
                keyboard.Listener.return_value.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
