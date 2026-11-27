"""Fake-portal tests; no actual display, input, or GI dependency."""
import threading
import unittest
from unittest.mock import Mock, patch

from macro_platform import DesktopUnavailable
from macro_wayland import (WaylandSession, GioPortal, PortalRequestError, REMOTE,
                           SCREEN, SESSION, REQUEST, REGISTRY)


class FakePortal:
    def __init__(self, stopped):
        self.stopped = stopped
        self.calls = []
        self.requests = []
        self.closed = False
        self.on_closed = None
        self.revoke = False
        self.denial = False
        self.fail_method = None
        self.grant = {"devices": 3, "streams": [
            (88, {"source_type": 1, "position": (0, 0), "size": (1920, 1080)})]}

    def assert_owner(self):
        pass

    def variant(self, signature, value):
        return value

    def path(self, kind, token):
        return f"/portal/{kind}/{token}"

    def subscribe(self, interface, signal, path, callback):
        self.on_closed = callback
        self.handle = path

    def request(self, interface, method, signature, args, options=None, **kwargs):
        self.requests.append((interface, method, signature, args, options))
        if method == "CreateSession":
            return {"session_handle": self.handle}
        if method == "Start":
            if self.denial:
                raise PortalRequestError(method, 1)
            return self.grant
        return {}

    def call(self, interface, method, signature, args, **kwargs):
        self.calls.append((interface, method, signature, args, kwargs))
        if method == self.fail_method:
            raise DesktopUnavailable("ambiguous delivery")

    def pump(self):
        if self.revoke and self.on_closed:
            self.on_closed(())

    def close(self):
        self.closed = True
        return True


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.portal = FakePortal(self.stop)
        self.session = WaylandSession("test.desktop", self.stop,
                                      portal_factory=lambda _: self.portal)

    def inputs(self):
        return [(method, args[2:]) for iface, method, sig, args, kw in self.portal.calls
                if method.startswith("Notify")]

    def test_negotiation_and_input(self):
        with self.session as session:
            self.assertEqual(session.logical_size, (1920, 1080))
            self.assertEqual(session.node, 88)
            session.move_absolute(100, 200)
            session.button("left", True)
            session.button("left", False)
            session.scroll(-2)
            session.key(0xffe1, True)
            session.key(97, True)
            session.key(97, False)
        self.assertEqual([(x[0], x[1]) for x in self.portal.requests],
                         [(REMOTE, "CreateSession"), (REMOTE, "SelectDevices"),
                          (SCREEN, "SelectSources"), (REMOTE, "Start")])
        self.assertEqual(self.portal.calls[0][:2], (REGISTRY, "Register"))
        self.assertEqual(self.inputs(), [
            ("NotifyPointerMotionAbsolute", (88, 100.0, 200.0)),
            ("NotifyPointerButton", (272, 1)),
            ("NotifyPointerButton", (272, 0)),
            ("NotifyPointerAxisDiscrete", (0, -2)),
            ("NotifyKeyboardKeysym", (0xffe1, 1)),
            ("NotifyKeyboardKeysym", (97, 1)),
            ("NotifyKeyboardKeysym", (97, 0)),
            ("NotifyKeyboardKeysym", (0xffe1, 0))])
        self.assertEqual(self.portal.calls[-1][:2], (SESSION, "Close"))
        self.assertTrue(self.portal.closed)
        with self.assertRaises(RuntimeError):
            self.session.__enter__()

    def test_read_only_session_never_requests_remote_desktop(self):
        session = WaylandSession("test.desktop", self.stop, devices=0,
                                 portal_factory=lambda _: self.portal)
        with session:
            for operation in (lambda: session.move_absolute(1, 1),
                              lambda: session.key(97, True),
                              lambda: session.button("left", True),
                              lambda: session.scroll(1)):
                with self.assertRaisesRegex(DesktopUnavailable, "not authorized"):
                    operation()
        self.assertEqual([(r[0], r[1]) for r in self.portal.requests],
                         [(SCREEN, "CreateSession"), (SCREEN, "SelectSources"),
                          (SCREEN, "Start")])
        self.assertFalse(self.inputs())
        self.assertTrue(self.portal.closed)

    def test_pointer_only_session_rejects_keyboard(self):
        self.portal.grant["devices"] = 2
        session = WaylandSession("test.desktop", self.stop, devices=2,
                                 portal_factory=lambda _: self.portal)
        with session:
            session.move_absolute(2, 3)
            with self.assertRaisesRegex(DesktopUnavailable, "not authorized"):
                session.key(97, True)
        self.assertEqual(self.portal.requests[1][4]["types"], 2)
        self.assertEqual(self.inputs(), [("NotifyPointerMotionAbsolute", (88, 2.0, 3.0))])

    def test_denial_closes_session_without_input(self):
        self.portal.denial = True
        with self.assertRaisesRegex(PortalRequestError, "cancelled"):
            with self.session:
                self.fail("denied session became active")
        self.assertFalse(self.inputs())
        self.assertTrue(self.portal.closed)

    def test_partial_grant_rejected(self):
        self.portal.grant["devices"] = 1
        with self.assertRaisesRegex(DesktopUnavailable, "both required"):
            with self.session:
                self.fail("partial grant became active")
        self.assertFalse(self.inputs())
        self.assertTrue(self.portal.closed)

    def test_bad_geometry_rejected(self):
        self.portal.grant["streams"][0][1]["position"] = (1920, 0)
        with self.assertRaisesRegex(DesktopUnavailable, "geometry"):
            with self.session:
                self.fail("unsupported geometry became active")
        self.assertFalse(self.inputs())
        self.assertTrue(self.portal.closed)

    def test_stop_releases_held_inputs_and_blocks_new_input(self):
        with self.session as session:
            session.key(0xffe1, True)
            session.button("left", True)
            self.stop.set()
            with self.assertRaisesRegex(RuntimeError, "Stopped"):
                session.key(97, True)
        self.assertEqual(self.inputs(), [
            ("NotifyKeyboardKeysym", (0xffe1, 1)),
            ("NotifyPointerButton", (272, 1)),
            ("NotifyPointerButton", (272, 0)),
            ("NotifyKeyboardKeysym", (0xffe1, 0))])

    def test_revocation_prevents_all_further_input(self):
        with self.session as session:
            session.key(0xffe1, True)
            self.portal.revoke = True
            with self.assertRaisesRegex(DesktopUnavailable, "revoked"):
                session.move_absolute(2, 3)
        self.assertEqual(self.inputs(), [("NotifyKeyboardKeysym", (0xffe1, 1))])
        self.assertTrue(self.portal.closed)

    def test_invalid_inputs_do_not_dispatch(self):
        with self.session as session:
            for point in ((-1, 0), (1920, 0), (0, 1080), (float("nan"), 1)):
                with self.assertRaises(DesktopUnavailable):
                    session.move_absolute(*point)
            for operation in (lambda: session.key(-1, True),
                              lambda: session.button("other", True),
                              lambda: session.scroll(101)):
                with self.assertRaises(ValueError):
                    operation()
        self.assertFalse(self.inputs())

    def test_ambiguous_press_fails_closed(self):
        with self.session as session:
            self.portal.fail_method = "NotifyKeyboardKeysym"
            with self.assertRaises(DesktopUnavailable):
                session.key(97, True)
            self.portal.fail_method = None
            with self.assertRaises(DesktopUnavailable):
                session.button("left", True)
        self.assertEqual(self.inputs(), [("NotifyKeyboardKeysym", (97, 1)),
                                         ("NotifyKeyboardKeysym", (97, 0))])

    def test_pipewire_remote_can_open_only_once(self):
        self.portal.open_pipewire_remote = Mock(return_value=123)
        with self.session as session:
            self.assertEqual(session.open_pipewire_remote(), 123)
            self.portal.open_pipewire_remote.assert_called_once_with(session.handle)
            with self.assertRaisesRegex(DesktopUnavailable, "already opened"):
                session.open_pipewire_remote()

    def test_revocation_during_remote_open_closes_received_fd(self):
        def open_remote(handle):
            self.portal.revoke = True
            return 123
        self.portal.open_pipewire_remote = Mock(side_effect=open_remote)
        with self.session as session, patch("macro_wayland.os.close") as close_fd:
            with self.assertRaisesRegex(DesktopUnavailable, "revoked"):
                session.open_pipewire_remote()
            close_fd.assert_called_once_with(123)
        self.assertTrue(self.session.broken)

    def test_conflicting_logical_dimensions_rejected(self):
        self.portal.grant["streams"][0][1]["logical_size"] = (960, 540)
        with self.assertRaisesRegex(DesktopUnavailable, "geometry"):
            with self.session:
                self.fail("inconsistent dimensions")

    def test_cancelled_before_open_does_not_connect(self):
        self.stop.set()
        self.session.portal_factory = Mock(side_effect=AssertionError("connected"))
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            with self.session:
                self.fail("cancelled session became active")
        self.session.portal_factory.assert_not_called()


class RequestTests(unittest.TestCase):
    def client(self, response=None, stop=False):
        # Exercise the real request ordering/cleanup without Gio.
        client = GioPortal.__new__(GioPortal)
        client.owner = threading.get_ident()
        client.stopped = threading.Event()
        client.variant = lambda sig, value: value
        client.path = lambda kind, token: f"/request/{token}"
        callbacks = []
        client.subscribe = Mock(side_effect=lambda *args: callbacks.append(args[-1]) or 1)
        client.unsubscribe = Mock()

        def call(interface, method, signature, args, **kwargs):
            if method == "Start":
                self.assertTrue(callbacks)
                if stop:
                    client.stopped.set()
                else:
                    callbacks[0](response)
                return (client.path("request", args[-1]["handle_token"]),)
            return ()
        client.call = Mock(side_effect=call)
        client.pump = Mock()
        return client

    def test_response_subscribed_before_request(self):
        client = self.client((0, {"devices": 3}))
        self.assertEqual(client.request(REMOTE, "Start", "(a{sv})", ()),
                         {"devices": 3})
        client.unsubscribe.assert_called_once_with(1)
        self.assertEqual(client.call.call_count, 1)

    def test_cancellation_response_is_not_a_success(self):
        client = self.client((1, {}))
        with self.assertRaises(PortalRequestError) as ctx:
            client.request(REMOTE, "Start", "(a{sv})", ())
        self.assertEqual(ctx.exception.code, 1)
        client.unsubscribe.assert_called_once_with(1)

    def test_stop_closes_outstanding_request(self):
        client = self.client(stop=True)
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            client.request(REMOTE, "Start", "(a{sv})", ())
        self.assertEqual(client.call.call_args.args[:2], (REQUEST, "Close"))
        client.unsubscribe.assert_called_once_with(1)
