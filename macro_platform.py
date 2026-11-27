"""Lazy desktop integration boundary for the supported legacy platforms.

Automation follows the existing PyAutoGUI method contract so callers can
continue injecting fake implementations. Native Wayland playback is opt-in during QA.
"""
import os
import sys


DESKTOP_ACTIONS = frozenset({
    "click", "move", "drag", "scroll", "key", "key_down", "key_up",
    "click_image", "watch_start", "wait_until", "if_start", "until_start",
    "clipboard_paste", "find_text", "wait_text",
})


def wayland_trial_enabled():
    return (desktop_platform() == "wayland" and
            os.environ.get("MACRORUNNER_WAYLAND_EXPERIMENTAL") == "1")


class DesktopUnavailable(RuntimeError):
    """A desktop capability is not available on the current platform."""


def desktop_platform(platform_name=None, environ=None):
    """Classify the desktop session without importing native integrations."""
    platform_name = sys.platform if platform_name is None else platform_name
    environ = os.environ if environ is None else environ
    if platform_name == "win32":
        return "windows"
    if not platform_name.startswith("linux"):
        return "unsupported"
    session = environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland" or (session != "x11" and environ.get("WAYLAND_DISPLAY")):
        return "wayland"
    return "x11" if environ.get("DISPLAY") else "unavailable"


def require_legacy_desktop(capability):
    platform = desktop_platform()
    if platform in ("windows", "x11"):
        return
    if platform == "wayland":
        raise DesktopUnavailable(f"{capability} is not yet supported on Wayland. "
                                 "Use an X11/Xorg session.")
    if platform == "unavailable":
        raise DesktopUnavailable(f"{capability} requires an available X11 display.")
    raise DesktopUnavailable(f"{capability} supports Windows and Linux X11 only.")


def get_automation():
    """Return the legacy mouse, keyboard and screenshot implementation."""
    require_legacy_desktop("Desktop automation")
    import pyautogui
    return pyautogui


def create_hotkeys(bindings):
    require_legacy_desktop("Global hotkeys")
    from pynput import keyboard
    return keyboard.GlobalHotKeys(bindings)


def create_mouse_listener(**callbacks):
    require_legacy_desktop("Global recording")
    from pynput import mouse
    return mouse.Listener(**callbacks)


def create_keyboard_listener(**callbacks):
    require_legacy_desktop("Global recording")
    from pynput import keyboard
    return keyboard.Listener(**callbacks)
