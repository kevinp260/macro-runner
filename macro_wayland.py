"""Native Wayland portal transport and authorized input primitives.

One session, one worker thread, one selected monitor. This module deliberately
does not enable workflow playback; capture and runtime lifecycle follow.
"""
import math
import threading
import time
import uuid

from macro_platform import DesktopUnavailable, desktop_platform

SERVICE = "org.freedesktop.portal.Desktop"
ROOT = "/org/freedesktop/portal/desktop"
PREFIX = "org.freedesktop.portal."
REMOTE = PREFIX + "RemoteDesktop"
SCREEN = PREFIX + "ScreenCast"
SESSION = PREFIX + "Session"
REQUEST = PREFIX + "Request"
REGISTRY = "org.freedesktop.host.portal.Registry"
DEVICES = 3  # keyboard | pointer
BUTTONS = {"left": 272, "right": 273, "middle": 274}


class PortalRequestError(DesktopUnavailable):
    def __init__(self, method, code):
        self.code = code
        reason = "cancelled" if code == 1 else "failed"
        super().__init__(f"Wayland portal {method} {reason} (response {code}).")


class GioPortal:
    """Private bus connection; callbacks are dispatched on its owning worker."""

    def __init__(self, stopped):
        if desktop_platform() != "wayland":
            raise DesktopUnavailable("Native Wayland portal requires a Wayland session.")
        try:
            from gi.repository import Gio, GLib
        except (ImportError, ValueError) as exc:
            raise DesktopUnavailable("Wayland requires system PyGObject (python3-gi).") from exc
        self.gio, self.glib = Gio, GLib
        self.variant = GLib.Variant
        self.stopped = stopped
        self.owner = threading.get_ident()
        self.context = GLib.MainContext.new()
        self.subscriptions = set()
        self.connection = None
        try:
            address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            flags = (Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                     Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION)
            self.connection = Gio.DBusConnection.new_for_address_sync(
                address, flags, None, None)
            self.connection.set_exit_on_close(False)
        except GLib.Error as exc:
            self.close()
            raise DesktopUnavailable("Cannot connect to the Wayland desktop portal.") from exc

    def assert_owner(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError("Wayland portal must stay on its owning worker thread.")

    def path(self, kind, token):
        self.assert_owner()
        sender = self.connection.get_unique_name()[1:].replace(".", "_")
        return f"{ROOT}/{kind}/{sender}/{token}"

    def call(self, interface, method, signature, args, *, path=ROOT, timeout=5000):
        self.assert_owner()
        try:
            result = self.connection.call_sync(
                SERVICE, path, interface, method, self.variant(signature, args),
                None, self.gio.DBusCallFlags.NONE, timeout, None)
            return result.unpack()
        except self.glib.Error as exc:
            raise DesktopUnavailable(f"Wayland portal {method} failed.") from exc

    def subscribe(self, interface, signal, path, callback):
        self.assert_owner()
        self.context.push_thread_default()
        try:
            token = self.connection.signal_subscribe(
                SERVICE, interface, signal, path, None,
                self.gio.DBusSignalFlags.NONE,
                lambda conn, sender, obj, iface, sig, params: callback(params.unpack()))
            self.subscriptions.add(token)
            return token
        finally:
            self.context.pop_thread_default()

    def unsubscribe(self, token):
        self.assert_owner()
        self.connection.signal_unsubscribe(token)
        self.subscriptions.discard(token)

    def pump(self):
        self.assert_owner()
        # Bound dispatch work even when unrelated events keep arriving.
        for _ in range(64):
            if not self.context.pending():
                break
            self.context.iteration(False)

    def request(self, interface, method, signature, args, options=None,
                session_closed=lambda: False):
        """Subscribe before the method call; close abandoned request handles."""
        self.assert_owner()
        if self.stopped.is_set():
            raise RuntimeError("Stopped")
        token = "r" + uuid.uuid4().hex
        expected = self.path("request", token)
        response = []
        subscription = self.subscribe(REQUEST, "Response", expected, response.append)
        handle = expected
        completed = False
        try:
            options = dict(options or {}, handle_token=self.variant("s", token))
            handle, = self.call(interface, method, signature, (*args, options))
            if handle != expected:
                raise DesktopUnavailable("Unexpected Wayland portal request handle.")
            deadline = time.monotonic() + 90
            closed_deadline = None
            while True:
                self.pump()
                if self.stopped.is_set():
                    raise RuntimeError("Stopped")
                if response:
                    code, result = response[0]
                    completed = True
                    if code:
                        raise PortalRequestError(method, code)
                    return result
                now = time.monotonic()
                if session_closed() and closed_deadline is None:
                    # Session.Closed and a cancellation response can race.
                    closed_deadline = now + 2
                if now >= deadline or (closed_deadline is not None and now >= closed_deadline):
                    raise DesktopUnavailable(f"Wayland portal {method} response unavailable.")
                self.stopped.wait(.02)
        finally:
            if not completed:
                try:
                    self.call(REQUEST, "Close", "()", (), path=handle, timeout=1000)
                except DesktopUnavailable:
                    pass  # Closing the private bus is the final fallback.
            self.unsubscribe(subscription)

    def close(self):
        self.assert_owner()
        if self.connection is None:
            return True
        connection = self.connection
        ok = True
        try:
            for token in tuple(self.subscriptions):
                try:
                    self.unsubscribe(token)
                except Exception:
                    ok = False
            try:
                if not connection.is_closed():
                    connection.close_sync(None)
            except self.glib.Error:
                ok = False
        finally:
            self.connection = None
            self.subscriptions.clear()
        return ok


class WaylandSession:
    """Consent-scoped logical-coordinate input; close on the owning worker.

    Callers must use a context manager (or close in finally). No session reuse,
    persistence, automatic authorization or global shortcut registration.
    """

    def __init__(self, app_id, stopped, *, portal_factory=GioPortal):
        if not isinstance(app_id, str) or not app_id.strip():
            raise ValueError("An installed desktop application ID is required.")
        self.app_id = app_id
        self.stopped = stopped
        self.portal_factory = portal_factory
        self.portal = None
        self.handle = None
        self.node = None
        self.logical_size = None
        self.revoked = False
        self.broken = False
        self.active = False
        self.used = False
        self.held = []

    def __enter__(self):
        if self.used:
            raise RuntimeError("A Wayland session cannot be restarted.")
        self.used = True
        if self.stopped.is_set():
            raise RuntimeError("Stopped")
        self.portal = self.portal_factory(self.stopped)
        try:
            self._negotiate()
            return self
        except BaseException:
            self.close()
            raise

    def _request(self, interface, method, signature, args, options=None):
        result = self.portal.request(interface, method, signature, args, options,
                                     session_closed=lambda: self.revoked)
        if self.stopped.is_set():
            raise RuntimeError("Stopped")
        if self.revoked:
            raise DesktopUnavailable("Wayland desktop permission was revoked.")
        return result

    def _on_closed(self, params):
        self.revoked = True

    def _negotiate(self):
        p = self.portal
        v = p.variant
        p.call(REGISTRY, "Register", "(sa{sv})", (self.app_id, {}))
        token = "s" + uuid.uuid4().hex
        self.handle = p.path("session", token)
        p.subscribe(SESSION, "Closed", self.handle, self._on_closed)
        result = self._request(REMOTE, "CreateSession", "(a{sv})", (),
                               {"session_handle_token": v("s", token)})
        if result.get("session_handle") != self.handle:
            raise DesktopUnavailable("Unexpected Wayland portal session handle.")
        self._request(REMOTE, "SelectDevices", "(oa{sv})", (self.handle,),
                      {"types": v("u", DEVICES)})
        self._request(SCREEN, "SelectSources", "(oa{sv})", (self.handle,),
                      {"types": v("u", 1), "multiple": v("b", False),
                       "cursor_mode": v("u", 1)})
        result = self._request(REMOTE, "Start", "(osa{sv})", (self.handle, ""))
        if result.get("devices", 0) & DEVICES != DEVICES:
            raise DesktopUnavailable("Keyboard and pointer permission are both required.")
        streams = result.get("streams", [])
        if len(streams) != 1:
            raise DesktopUnavailable("Select exactly one monitor for Wayland automation.")
        node, metadata = streams[0]
        size = metadata.get("size", ())
        if (metadata.get("source_type") != 1 or
                tuple(metadata.get("position", ())) != (0, 0) or
                len(size) != 2 or any(type(n) is not int or n <= 0 for n in size) or
                type(node) is not int or not 0 < node <= 0xffffffff):
            raise DesktopUnavailable("Wayland requires a monitor at desktop origin with valid geometry.")
        self.node, self.logical_size = node, tuple(size)
        self.active = True
        self.check()

    def check(self):
        if not self.active or self.broken:
            raise DesktopUnavailable("Wayland desktop session is not active.")
        self.portal.pump()
        if self.stopped.is_set():
            raise RuntimeError("Stopped")
        if self.revoked:
            raise DesktopUnavailable("Wayland desktop permission was revoked.")

    def _send(self, method, signature, args):
        self.check()
        self._dispatch(method, signature, args)

    def _dispatch(self, method, signature, args):
        try:
            self.portal.call(REMOTE, method, signature,
                             (self.handle, {}, *args), timeout=1000)
        except Exception:
            # An ambiguous input error must not be retried or skipped.
            self.broken = True
            raise

    def move_absolute(self, x, y):
        self.check()
        w, h = self.logical_size
        if (type(x) not in (int, float) or type(y) not in (int, float) or
                not math.isfinite(x) or not math.isfinite(y) or
                not 0 <= x < w or not 0 <= y < h):
            raise DesktopUnavailable("Pointer target is outside the authorized monitor.")
        self._send("NotifyPointerMotionAbsolute", "(oa{sv}udd)",
                   (self.node, float(x), float(y)))

    @staticmethod
    def _event(kind, code, state):
        method = "NotifyKeyboardKeysym" if kind == "key" else "NotifyPointerButton"
        return method, "(oa{sv}iu)", (code, state)

    def _change_held(self, kind, code, pressed):
        self.check()
        item = (kind, code)
        if pressed:
            if item in self.held:
                return
            # Record before dispatch: a failed reply may follow a delivered press.
            self.held.append(item)
            self._dispatch(*self._event(kind, code, 1))
        elif item in self.held:
            self._dispatch(*self._event(kind, code, 0))
            self.held.remove(item)

    def key(self, keysym, pressed):
        if type(keysym) is not int or not 0 < keysym <= 0x1fffffff:
            raise ValueError("Invalid keyboard symbol.")
        if type(pressed) is not bool:
            raise ValueError("Key state must be boolean.")
        self._change_held("key", keysym, pressed)

    def button(self, name, pressed):
        if name not in BUTTONS or type(pressed) is not bool:
            raise ValueError("Invalid pointer button or state.")
        self._change_held("button", BUTTONS[name], pressed)

    def scroll(self, steps):
        # Native portal convention: axis 0 is vertical, signed discrete steps.
        if type(steps) is not int or not -100 <= steps <= 100:
            raise ValueError("Scroll requires at most 100 signed steps per call.")
        if steps:
            self._send("NotifyPointerAxisDiscrete", "(oa{sv}ui)", (0, steps))

    def close(self):
        p = self.portal
        if p is None:
            return True
        p.assert_owner()
        ok = True
        try:
            p.pump()
            if self.active and not self.revoked:
                # Only releases are allowed during cleanup, including after Stop.
                for kind, code in reversed(self.held):
                    try:
                        p.pump()
                        if self.revoked:
                            break
                        self._dispatch(*self._event(kind, code, 0))
                    except Exception:
                        ok = False
            if self.handle and not self.revoked:
                try:
                    p.call(SESSION, "Close", "()", (), path=self.handle, timeout=1000)
                except DesktopUnavailable:
                    ok = False
        finally:
            try:
                ok = p.close() and ok
            finally:
                self.portal = None
                self.active = False
                self.held.clear()
        return ok

    def __exit__(self, exc_type, exc, traceback):
        if not self.close() and exc_type is None:
            raise DesktopUnavailable("Wayland session cleanup could not be confirmed.")
        return False
