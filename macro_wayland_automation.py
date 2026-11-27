"""Workflow adapter over authorized native Wayland input and capture.

Timed moves start at a fresh authorized cursor observation. Drag starts
from the explicit commanded point. Keep hands off during playback.
"""
import math

from macro_keys import ALIASES, MODIFIERS
from macro_platform import DesktopUnavailable
from macro_wayland import WaylandSession
from macro_wayland_capture import WaylandCapture

APP_ID = "io.github.kevinp260.MacroRunner"
SPECIAL_KEYS = {
    "backspace": 0xff08, "tab": 0xff09, "enter": 0xff0d, "esc": 0xff1b,
    "home": 0xff50, "left": 0xff51, "up": 0xff52, "right": 0xff53,
    "down": 0xff54, "pgup": 0xff55, "pgdn": 0xff56, "end": 0xff57,
    "insert": 0xff63, "delete": 0xffff, "printscreen": 0xff61,
    "numlock": 0xff7f, "capslock": 0xffe5, "shift": 0xffe1,
    "ctrl": 0xffe3, "alt": 0xffe9, "win": 0xffeb, "space": 32,
}


def key_symbol(name):
    name = name.lower()
    name = ALIASES.get(name, name)
    if name in SPECIAL_KEYS:
        return SPECIAL_KEYS[name]
    if len(name) == 1 and 33 <= ord(name) <= 126:
        return ord(name)
    if name.startswith("f") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 24:
            return 0xffbd + number
    raise DesktopUnavailable("Unsupported Wayland key name.")


def text_symbol(character):
    if character in ("\n", "\r"):
        return SPECIAL_KEYS["enter"]
    if character == "\t":
        return SPECIAL_KEYS["tab"]
    if len(character) == 1 and 32 <= ord(character) <= 126:
        return ord(character)
    raise DesktopUnavailable("Wayland typed text currently supports printable ASCII, Tab and Enter only.")


def validate_wayland_action(action):
    """Validate literals before consent and resolved values before execution."""
    if action.kind in ("wait_window", "clipboard_read", "clipboard_set", "clipboard_paste"):
        raise DesktopUnavailable("Window waits and clipboard actions are not enabled in the Wayland trial.")
    if action.kind not in ("key", "key_down", "key_up") or "keys" in action.bindings:
        return
    if action.kind == "key" and action.key_mode == "type":
        for character in action.keys:
            text_symbol(character)
    else:
        names = [name.strip() for name in action.keys.split("+") if name.strip()]
        if not names:
            raise DesktopUnavailable("Unsupported Wayland key combination.")
        symbols = [key_symbol(name) for name in names]
        if len(set(symbols)) != len(symbols):
            raise DesktopUnavailable("Duplicate keys in Wayland key combination.")


class WaylandAutomation:
    """One managed backend per run. All native calls stay on the worker."""

    def __init__(self, gate, screen_size, invalidated, *,
                 session_factory=WaylandSession, capture_factory=WaylandCapture):
        self.gate = gate
        self.screen_size = screen_size
        self.invalidated = invalidated
        self.session = session_factory(APP_ID, gate.stopped, cursor_mode=4)
        self.capture_factory = capture_factory
        self.capture = None
        self.pointer = None
        self.keys = set()
        self.cleanup_failed = False

    def _geometry_check(self):
        if self.invalidated.is_set():
            raise DesktopUnavailable("Display configuration changed during Wayland automation.")

    def __enter__(self):
        self._geometry_check()
        try:
            self.session.__enter__()
            if self.session.logical_size != self.screen_size:
                raise DesktopUnavailable("Authorized monitor differs from the editor display.")
            self.session.geometry_guard = self._geometry_check
            self.capture = self.capture_factory(self.session)
            self.capture.__enter__()
            # No input is permitted until an actual fresh, correctly sized
            # frame arrives from the selected monitor.
            self.capture.screenshot()
            self.check()
            return self
        except BaseException:
            self.close()
            raise

    def check(self):
        self._geometry_check()
        self.session.check()
        if self.gate.pause_pending and self.session.held:
            raise DesktopUnavailable("Wayland paused with held input; run stopped for safety.")
        if self.capture is not None:
            self.capture.check()

    def _ready(self):
        self.gate.wait(0)
        self.check()

    def _point(self, x, y):
        if (type(x) not in (int, float) or type(y) not in (int, float) or
                not 0 <= x < self.screen_size[0] or not 0 <= y < self.screen_size[1]):
            raise DesktopUnavailable("Pointer target is outside the authorized monitor.")

    def size(self):
        self.check()
        return self.screen_size

    def screenshot(self, region=None):
        self.check()
        return self.capture.screenshot(region)

    def moveTo(self, x, y, duration=0):
        self._point(x, y)
        self._ready()
        self._move(x, y, duration)

    def _move(self, x, y, duration, *, dragging=False):
        if not math.isfinite(duration) or duration < 0:
            raise DesktopUnavailable("Invalid Wayland move duration.")
        if duration == 0:
            self.session.move_absolute(x, y)
        else:
            if dragging:
                # The explicit drag origin was commanded before button down.
                start_x, start_y = self.pointer
            else:
                # Observe the real pointer at action time, after start delay.
                # Never guess from a previous command or silently jump.
                (start_x, start_y), _ = self.capture.pointer_sample()
                self._point(start_x, start_y)
                self.check()
            # At most 50 motion updates per second; never build a list of steps.
            count = max(1, math.ceil(duration / .02))
            for step in range(1, count + 1):
                self.gate.wait(duration / count, abort_on_pause=dragging)
                self.check()
                self.session.move_absolute(start_x + (x - start_x) * step / count,
                                           start_y + (y - start_y) * step / count)
        self.pointer = (x, y)

    def click(self, x=None, y=None, button="left"):
        if x is None and y is None:
            if self.pointer is None:
                raise DesktopUnavailable("Wayland click has no known target coordinates.")
            x, y = self.pointer
        self._point(x, y)
        self._ready()
        # Reassert the exact target immediately before each click.
        self._move(x, y, 0)
        if self.gate.pause_pending:
            raise DesktopUnavailable("Wayland click interrupted before button press.")
        self.session.button(button, True)
        self.session.button(button, False)

    def dragTo(self, x, y, duration=0, button="left"):
        self._point(x, y)
        self._ready()
        if self.pointer is None:
            raise DesktopUnavailable("Wayland drag has no known start coordinates.")
        self._move(*self.pointer, 0)
        if self.gate.pause_pending:
            raise DesktopUnavailable("Wayland drag interrupted before button press.")
        self.session.button(button, True)
        try:
            self._move(x, y, duration, dragging=True)
            self.session.button(button, False)
        except Exception as exc:
            # Stop/permission loss/pause must never leave a drag to resume
            # later or allow the workflow to skip an ambiguous input action.
            self.session.broken = True
            if str(exc) == "Stopped" or isinstance(exc, DesktopUnavailable):
                raise
            raise DesktopUnavailable("Wayland drag interrupted; run stopped.") from exc

    def scroll(self, amount):
        self._ready()
        # PyAutoGUI positive = up; portal axis 0 positive = down.
        remaining = -amount
        while remaining:
            self._ready()
            step = max(-100, min(100, remaining))
            self.session.scroll(step)
            remaining -= step

    def keyDown(self, name):
        symbol = key_symbol(name)
        self._ready()
        if symbol not in self.keys:
            self.session.key(symbol, True)
            self.keys.add(symbol)

    def keyUp(self, name):
        symbol = key_symbol(name)
        self._ready()
        if symbol not in self.keys:
            raise DesktopUnavailable("Wayland key was not held by this run.")
        self.session.key(symbol, False)
        self.keys.remove(symbol)

    def _chord(self, symbols):
        self._ready()
        modifiers = {SPECIAL_KEYS[name] for name in MODIFIERS}
        if any(symbol in self.keys and symbol not in modifiers for symbol in symbols):
            raise DesktopUnavailable("Cannot press a key that the Wayland run already holds.")
        temporary = []
        for symbol in symbols:
            if symbol not in self.keys:
                self.session.key(symbol, True)
                temporary.append(symbol)
        for symbol in reversed(temporary):
            self.session.key(symbol, False)

    def press(self, name):
        symbol = key_symbol(name)
        if symbol in self.keys:
            raise DesktopUnavailable("Cannot press a key that the Wayland run already holds.")
        self._chord([symbol])

    def hotkey(self, *names):
        symbols = [key_symbol(name) for name in names]
        if not symbols or len(set(symbols)) != len(symbols):
            raise DesktopUnavailable("Invalid Wayland key combination.")
        self._chord(symbols)

    def write(self, text):
        for symbol in [text_symbol(character) for character in text]:
            self._chord([symbol])

    def close(self):
        # Release input and revoke the portal first, before native pipeline
        # shutdown, which can block in a misbehaving GStreamer plugin.
        ok = True
        try:
            ok = self.session.close()
        except Exception:
            ok = False
        finally:
            if self.capture is not None:
                try:
                    ok = self.capture.close() and ok
                except Exception:
                    ok = False
                self.capture = None
            self.keys.clear()
            self.pointer = None
        self.cleanup_failed = self.cleanup_failed or not ok
        return not self.cleanup_failed

    def __exit__(self, exc_type, exc, traceback):
        if not self.close() and exc_type is None:
            raise DesktopUnavailable("Wayland backend cleanup could not be confirmed.")
        return False
