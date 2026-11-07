"""Foreground window targeting: Windows native API and Ubuntu/X11 EWMH.

Window selection and client geometry use physical desktop coordinates. No
background mouse/keyboard injection is attempted; Wayland is unsupported.
"""
import ctypes
from ctypes import wintypes
from ctypes.util import find_library
from dataclasses import dataclass, replace
import os
import sys
import time


class WindowUnavailable(RuntimeError):
    """Target is missing, ambiguous, occluded, or cannot be activated."""


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    class_name: str
    pid: int
    x: int
    y: int
    width: int
    height: int
    minimized: bool = False
    hidden: bool = False


def validate_target(value):
    """Validate optional version-2 workflow target settings without OS access."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
            "handle", "title", "class_name", "pid", "relative", "activate"}:
        raise ValueError("Window target has invalid fields.")
    if (isinstance(value["handle"], bool) or
            not isinstance(value["handle"], int) or value["handle"] < 1):
        raise ValueError("Window handle must be a positive integer.")
    if (isinstance(value["pid"], bool) or
            not isinstance(value["pid"], int) or value["pid"] < 0):
        raise ValueError("Window process identifier must be a nonnegative integer.")
    for key in ("title", "class_name"):
        if not isinstance(value[key], str) or len(value[key]) > 1024:
            raise ValueError("Window title/class must be text within 1024 characters.")
    if not value["title"].strip():
        raise ValueError("Target window must have a non-empty title.")
    if not isinstance(value["relative"], bool) or not isinstance(value["activate"], bool):
        raise ValueError("Window relative/activation settings must be true or false.")
    return dict(value)


def target_from_window(info, *, relative=True, activate=True):
    return validate_target({
        "handle": info.handle, "title": info.title,
        "class_name": info.class_name, "pid": info.pid,
        "relative": relative, "activate": activate,
    })


def identify_target(saved, windows):
    """Fail closed: exact instance first; reopened window only if unique."""
    spec = validate_target(saved)
    matches = [w for w in windows
               if w.title == spec["title"] and
               w.class_name == spec["class_name"]]
    exact = [w for w in matches if w.handle == spec["handle"] and
             (not spec["pid"] or w.pid == spec["pid"])]
    if len(exact) == 1:
        return exact[0]
    # Running window can change its title; same HWND + PID + class is
    # specific enough to keep the original instance.
    same_instance = [w for w in windows if w.handle == spec["handle"] and
                     w.class_name == spec["class_name"] and
                     spec["pid"] and w.pid == spec["pid"]]
    if len(same_instance) == 1:
        return same_instance[0]
    same_process = [w for w in matches if spec["pid"] and w.pid == spec["pid"]]
    if len(same_process) == 1:
        return same_process[0]
    if len(matches) == 1:
        return matches[0]  # Explicit fallback after restart/new PID/handle.
    if matches or same_process:
        raise WindowUnavailable(
            "Multiple windows match the saved target. Select the window again.")
    raise WindowUnavailable(
        "Target window was not found. Reopen it or select another target window.")


def _platform():
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            raise WindowUnavailable(
                "Window targeting is unavailable on Wayland. Use an X11/Xorg session.")
        if not os.environ.get("DISPLAY"):
            raise WindowUnavailable("X11 display is unavailable; window targeting cannot run.")
        return "x11"
    raise WindowUnavailable("Window targeting supports Windows and Ubuntu X11 only.")


class _Windows:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        u = self.user
        u.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        u.EnumWindows.restype = wintypes.BOOL
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.IsWindowVisible.restype = wintypes.BOOL
        u.IsIconic.argtypes = [wintypes.HWND]
        u.IsIconic.restype = wintypes.BOOL
        u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetClientRect.restype = wintypes.BOOL
        u.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        u.ClientToScreen.restype = wintypes.BOOL
        u.GetForegroundWindow.restype = wintypes.HWND
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.ShowWindow.restype = wintypes.BOOL

    def windows(self):
        return self._enumerate_windows(include_hidden=False)

    def all_windows(self):
        """Include hidden top-level windows so hidden differs from closed."""
        return self._enumerate_windows(include_hidden=True)

    def _enumerate_windows(self, *, include_hidden):
        result = []
        callback_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def collect(hwnd, unused):
            u = self.user
            visible = bool(u.IsWindowVisible(hwnd))
            if not visible and not include_hidden:
                return True
            length = u.GetWindowTextLengthW(hwnd)
            if not 0 < length <= 1024:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            if not u.GetWindowTextW(hwnd, title_buffer, length + 1):
                return True
            class_buffer = ctypes.create_unicode_buffer(256)
            u.GetClassNameW(hwnd, class_buffer, len(class_buffer))
            rect = wintypes.RECT()
            origin = wintypes.POINT(0, 0)
            if not u.GetClientRect(hwnd, ctypes.byref(rect)) or not u.ClientToScreen(
                    hwnd, ctypes.byref(origin)):
                return True
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if width < 1 or height < 1:
                return True
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            result.append(WindowInfo(int(hwnd), title_buffer.value, class_buffer.value,
                                     int(pid.value), origin.x, origin.y, width, height,
                                     bool(u.IsIconic(hwnd)),
                                     not visible or bool(u.IsIconic(hwnd))))
            return True

        callback = callback_t(collect)
        if not self.user.EnumWindows(callback, 0):
            raise WindowUnavailable("Unable to enumerate Windows desktop windows.")
        return result

    def foreground_handle(self):
        return int(self.user.GetForegroundWindow() or 0)

    def activate(self, handle):
        if self.user.IsIconic(handle):
            self.user.ShowWindow(handle, 9)  # SW_RESTORE
        self.user.SetForegroundWindow(handle)


class _X11:
    """Tiny libX11/EWMH adapter: no additional Python package dependency."""
    class Attributes(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_int), ("y", ctypes.c_int),
            ("width", ctypes.c_int), ("height", ctypes.c_int),
            ("border_width", ctypes.c_int), ("depth", ctypes.c_int),
            ("visual", ctypes.c_void_p), ("root", ctypes.c_ulong),
            ("klass", ctypes.c_int), ("bit_gravity", ctypes.c_int),
            ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
            ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong),
            ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
            ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int),
            ("all_event_masks", ctypes.c_long), ("your_event_mask", ctypes.c_long),
            ("do_not_propagate_mask", ctypes.c_long),
            ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p),
        ]

    class ClassHint(ctypes.Structure):
        _fields_ = [("res_name", ctypes.c_void_p), ("res_class", ctypes.c_void_p)]

    class ClientMessage(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_int), ("serial", ctypes.c_ulong),
            ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
            ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
            ("format", ctypes.c_int), ("data", ctypes.c_long * 5),
        ]

    def __init__(self):
        path = find_library("X11")
        if not path:
            raise WindowUnavailable("libX11 is not installed; window targeting unavailable.")
        x = ctypes.CDLL(path)
        for name, result, args in [
            ("XOpenDisplay", ctypes.c_void_p, [ctypes.c_char_p]),
            ("XCloseDisplay", ctypes.c_int, [ctypes.c_void_p]),
            ("XDefaultRootWindow", ctypes.c_ulong, [ctypes.c_void_p]),
            ("XInternAtom", ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]),
            ("XGetWindowProperty", ctypes.c_int, [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
                ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                ctypes.POINTER(ctypes.c_void_p)]),
            ("XGetWindowAttributes", ctypes.c_int, [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(self.Attributes)]),
            ("XTranslateCoordinates", ctypes.c_int, [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int,
                ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
                ctypes.POINTER(ctypes.c_ulong)]),
            ("XGetClassHint", ctypes.c_int, [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(self.ClassHint)]),
            ("XFetchName", ctypes.c_int, [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]),
            ("XSendEvent", ctypes.c_int, [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]),
            ("XFlush", ctypes.c_int, [ctypes.c_void_p]),
            ("XFree", ctypes.c_int, [ctypes.c_void_p]),
        ]:
            fn = getattr(x, name)
            fn.argtypes = args
            fn.restype = result
        self.x = x

    def _open(self):
        display = self.x.XOpenDisplay(None)
        if not display:
            raise WindowUnavailable("Cannot connect to X11 display.")
        return display

    def _atom(self, display, name):
        return self.x.XInternAtom(display, name.encode("ascii"), False)

    def _property(self, display, window, name):
        atom = self._atom(display, name)
        prop_type, fmt, count, left = (ctypes.c_ulong(), ctypes.c_int(),
                                       ctypes.c_ulong(), ctypes.c_ulong())
        data = ctypes.c_void_p()
        status = self.x.XGetWindowProperty(
            display, window, atom, 0, 4096, False, 0,
            ctypes.byref(prop_type), ctypes.byref(fmt),
            ctypes.byref(count), ctypes.byref(left), ctypes.byref(data))
        if status != 0:
            raise WindowUnavailable("X11 could not read window-manager properties.")
        try:
            if not data.value:
                return None
            if fmt.value == 32:
                values = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
                return [int(values[i]) for i in range(count.value)]
            if fmt.value == 8:
                return ctypes.string_at(data, count.value)
            return None
        finally:
            if data.value:
                self.x.XFree(data)

    def _window_info(self, display, window, root):
        attrs = self.Attributes()
        if not self.x.XGetWindowAttributes(display, window, ctypes.byref(attrs)):
            return None
        if attrs.width < 1 or attrs.height < 1:
            return None
        x, y, child = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
        if not self.x.XTranslateCoordinates(display, window, root, 0, 0,
                                            ctypes.byref(x), ctypes.byref(y),
                                            ctypes.byref(child)):
            return None
        title_bytes = self._property(display, window, "_NET_WM_NAME")
        if isinstance(title_bytes, bytes):
            title = title_bytes.decode("utf-8", errors="replace")
        else:
            name = ctypes.c_void_p()
            title = ""
            if self.x.XFetchName(display, window, ctypes.byref(name)) and name.value:
                try:
                    title = ctypes.string_at(name).decode("latin-1", errors="replace")
                finally:
                    self.x.XFree(name)
        if not title or len(title) > 1024:
            return None
        hint = self.ClassHint()
        classname = ""
        if self.x.XGetClassHint(display, window, ctypes.byref(hint)):
            try:
                if hint.res_class:
                    classname = ctypes.string_at(hint.res_class).decode("utf-8", "replace")
            finally:
                if hint.res_name:
                    self.x.XFree(hint.res_name)
                if hint.res_class:
                    self.x.XFree(hint.res_class)
        pid_prop = self._property(display, window, "_NET_WM_PID")
        pid = int(pid_prop[0]) if isinstance(pid_prop, list) and pid_prop else 0
        unmapped = attrs.map_state != 2
        return WindowInfo(window, title, classname[:1024], pid,
                          x.value, y.value, attrs.width, attrs.height,
                          unmapped, unmapped)

    def windows(self):
        display = self._open()
        try:
            root = self.x.XDefaultRootWindow(display)
            handles = self._property(display, root, "_NET_CLIENT_LIST")
            if handles is None:
                raise WindowUnavailable(
                    "X11 window manager does not expose _NET_CLIENT_LIST.")
            result = []
            for window in handles:
                try:
                    info = self._window_info(display, window, root)
                except WindowUnavailable:
                    continue
                if info is not None:
                    result.append(info)
            return result
        finally:
            self.x.XCloseDisplay(display)

    def all_windows(self):
        # EWMH keeps managed clients in _NET_CLIENT_LIST even when unmapped
        # on compliant window managers. Some WMs omit hidden clients; this
        # is a documented backend limitation, not evidence they were closed.
        return self.windows()

    def foreground_handle(self):
        display = self._open()
        try:
            root = self.x.XDefaultRootWindow(display)
            active = self._property(display, root, "_NET_ACTIVE_WINDOW")
            return active[0] if isinstance(active, list) and active else 0
        finally:
            self.x.XCloseDisplay(display)

    def activate(self, handle):
        display = self._open()
        try:
            root = self.x.XDefaultRootWindow(display)
            class Event(ctypes.Union):
                _fields_ = [("xclient", self.ClientMessage),
                            ("pad", ctypes.c_long * 24)]
            event = Event()
            event.xclient.type = 33  # ClientMessage
            event.xclient.display = display
            event.xclient.window = handle
            event.xclient.message_type = self._atom(display, "_NET_ACTIVE_WINDOW")
            event.xclient.format = 32
            event.xclient.data[0] = 2  # Application request
            mask = (1 << 19) | (1 << 20)  # SubstructureNotify/Redirect
            if not self.x.XSendEvent(display, root, False, mask, ctypes.byref(event)):
                raise WindowUnavailable("X11 rejected the activation request.")
            self.x.XFlush(display)
        finally:
            self.x.XCloseDisplay(display)


class WindowManager:
    def __init__(self, backend=None):
        if backend is None:
            backend = _Windows() if _platform() == "windows" else _X11()
        self.backend = backend

    def windows(self):
        return self.backend.windows()

    def all_windows(self):
        getter = getattr(self.backend, "all_windows", None)
        if getter is None:
            raise WindowUnavailable(
                "The desktop backend cannot inspect hidden or closed windows.")
        return getter()

    def foreground_handle(self):
        return self.backend.foreground_handle()

    def activate(self, handle):
        self.backend.activate(handle)


class WindowBinding:
    """Per-run target: resolve fresh geometry and verify foreground before input."""

    def __init__(self, saved, manager=None):
        self.spec = validate_target(saved)
        self.manager = manager or WindowManager()

    def resolve(self):
        return identify_target(self.spec, self.manager.windows())

    def prepare(self, gate=None):
        window = self.resolve()
        if window.width < 1 or window.height < 1:
            raise WindowUnavailable("Target window has no usable client area.")
        if self.manager.foreground_handle() != window.handle or window.minimized:
            if not self.spec["activate"]:
                raise WindowUnavailable(
                    "Target window is not foreground. Enable 'Activate target' "
                    "or bring it to the front before running.")
            self.manager.activate(window.handle)
            # Window managers may delay or refuse activation. No global input
            # is sent until foreground is confirmed, never to an occluded app.
            for _ in range(20):
                if gate is not None:
                    gate.wait(0.05)
                else:
                    time.sleep(0.05)
                if self.manager.foreground_handle() == window.handle:
                    break
            else:
                raise WindowUnavailable(
                    "Could not activate the selected window. No input was sent.")
            # A restored window may have a different client origin/size
            # than its minimized placeholder geometry.
            window = self.resolve()
            if window.minimized:
                raise WindowUnavailable("Target window could not be restored.")
        return window

    def point(self, x, y, window):
        if not 0 <= x < window.width or not 0 <= y < window.height:
            raise WindowUnavailable(
                "Client-relative point is outside the target window. "
                "Check its size or action coordinates.")
        return window.x + x, window.y + y

    def rect(self, x, y, width, height, window):
        if (x < 0 or y < 0 or width < 1 or height < 1 or
                x + width > window.width or y + height > window.height):
            raise WindowUnavailable(
                "Client-relative region extends beyond the target window.")
        return window.x + x, window.y + y, width, height

    def transform(self, action, window):
        if not self.spec["relative"]:
            return action
        if action.kind in ("click", "move", "drag"):
            x, y = self.point(action.x, action.y, window)
            changes = {"x": x, "y": y}
            if action.kind == "drag":
                changes["to_x"], changes["to_y"] = self.point(
                    action.to_x, action.to_y, window)
            return replace(action, **changes)
        if action.kind in ("click_image", "wait_until", "if_start", "until_start",
                           "watch_start"):
            if action.kind != "watch_start" and action.condition_source == "pixel":
                x, y = self.point(action.pixel_x, action.pixel_y, window)
                return replace(action, pixel_x=x, pixel_y=y)
            if action.region_x is None:
                return replace(action, region_x=window.x, region_y=window.y,
                               region_w=window.width, region_h=window.height)
            x, y, w, h = self.rect(
                action.region_x, action.region_y, action.region_w, action.region_h,
                window)
            return replace(action, region_x=x, region_y=y, region_w=w, region_h=h)
        return action
