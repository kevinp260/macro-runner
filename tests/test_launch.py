"""Pure launch validation, argument, OS dispatch and runtime tests."""
from dataclasses import asdict
from pathlib import Path
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from macro_launch import LaunchError, arguments_list, launch_target, validate_launch
from macro_model import Action, parse_document, serialize_document, validate_action
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor
from macro_workflow import default_node
from macro_qt_workflow import description
from macro_windows import WindowInfo, target_from_window


class FakeDesktop:
    def keyDown(self, *_): pass
    def keyUp(self, *_): pass


class LaunchActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.executable = self.root / "Tool ñ + space.exe"
        self.executable.write_bytes(b"not actually run")
        self.executable.chmod(0o755)
        self.document = self.root / "Notes 日本語.txt"
        self.document.write_text("test", encoding="utf-8")

    def test_default_is_editable_but_not_executable_until_configured(self):
        action = default_node("launch").action
        self.assertEqual(action.kind, "launch")
        self.assertEqual(action.launch_target, "")
        self.assertEqual(validate_action(asdict(action)), action)
        errors = inspect_workflow([action])
        self.assertTrue(any(e.severity == "error" and e.index == 0
                            for e in errors))

    def test_roundtrip_and_legacy_compatibility(self):
        original = [Action(kind="launch", launch_mode="application",
                           launch_target=str(self.executable),
                           launch_args="--name\nMy Folder ñ"),
                    Action(kind="wait", seconds=1)]
        doc = serialize_document(original, 2, .5)
        self.assertEqual(parse_document(doc)[0], original)
        self.assertEqual(parse_document([
            {"kind": "wait", "seconds": 1}])[0][0].kind, "wait")
        self.assertIn("Tool ñ + space.exe", description(original[0]))
        self.assertNotIn("My Folder ñ", description(original[0]))

    def test_arguments_are_literal_without_shell_quote_expansion(self):
        args = "--folder\nA path with spaces\nname=José 🐈\n; touch /tmp/unsafe\n\n"
        self.assertEqual(arguments_list(args),
                         ["--folder", "A path with spaces",
                          "name=José 🐈", "; touch /tmp/unsafe"])
        action = Action(kind="launch", launch_target=str(self.executable),
                        launch_args=args)
        process = Mock()
        fake_popen = Mock(return_value=process)
        launch_target(action, platform_name="linux", popen=fake_popen)
        argv = fake_popen.call_args.args[0]
        self.assertEqual(argv, [str(self.executable), *arguments_list(args)])
        self.assertIs(fake_popen.call_args.kwargs["shell"], False)
        self.assertEqual(fake_popen.call_args.kwargs["stdin"], -3)
        self.assertFalse(process.poll.called)

    def test_windows_executable_passes_unicode_and_spaced_arguments_as_argv(self):
        action = Action(kind="launch", launch_target=str(self.executable),
                        launch_args="--label\nNew name 🐈\nC:\\Program Files\\Example")
        proc = Mock()
        fake = Mock(return_value=proc)
        launch_target(action, platform_name="win32", popen=fake)
        self.assertEqual(fake.call_args.args[0],
                         [str(self.executable), "--label", "New name 🐈",
                          r"C:\Program Files\Example"])
        self.assertIs(fake.call_args.kwargs["shell"], False)

    def test_win_file_default_opener_receives_literal_unicode_path(self):
        opener, fake = Mock(), Mock()
        action = Action(kind="launch", launch_mode="file",
                        launch_target=str(self.document))
        launch_target(action, platform_name="win32",
                      startfile=opener, popen=fake)
        opener.assert_called_once_with(str(self.document))
        fake.assert_not_called()

    def test_linux_default_opener_and_process_failure(self):
        target = "https://example.com/search?q=%E2%9C%93"
        app = Action(kind="launch", launch_mode="url", launch_target=target)
        p = Mock()
        p.poll.return_value = None
        call = Mock(return_value=p)
        launch_target(app, platform_name="linux", popen=call,
                      find_command=lambda cmd: "/usr/bin/xdg-open")
        self.assertEqual(call.call_args.args[0], ["/usr/bin/xdg-open", target])
        self.assertFalse(call.call_args.kwargs["shell"])
        p.poll.return_value = 3
        with self.assertRaisesRegex(LaunchError, "default application"):
            launch_target(app, platform_name="linux", popen=call,
                          find_command=lambda cmd: "/usr/bin/xdg-open")
        with self.assertRaisesRegex(LaunchError, "xdg-open"):
            launch_target(app, platform_name="linux", popen=call,
                          find_command=lambda cmd: None)

    def test_http_scheme_and_malformed_urls_rejected(self):
        for invalid in ("file:///tmp/a", "javascript:alert(1)", "data:text/plain,a",
                        "https://", "https://example.com:bad",
                        "https://example.com:99999", " https://example.com",
                        "https://example.com/a b",
                        "https://user:pass@example.com",
                        "https://example.com/\nmore"):
            with self.subTest(url=invalid), self.assertRaises(LaunchError):
                validate_launch(Action(kind="launch", launch_mode="url",
                                       launch_target=invalid))
        for valid in ("https://example.com/path?q=a%20b",
                      "http://localhost:8080/", "https://münchen.example/"):
            self.assertEqual(validate_launch(Action(
                kind="launch", launch_mode="url", launch_target=valid)), valid)

    def test_relative_invalid_and_missing_files_rejected(self):
        for target in ("relative.exe", "notes/text.txt"):
            with self.subTest(target=target), self.assertRaises(LaunchError):
                validate_launch(Action(kind="launch", launch_target=target))
        missing = Action(kind="launch", launch_target=str(self.root / "missing.exe"))
        with self.assertRaisesRegex(LaunchError, "does not exist"):
            validate_launch(missing, check_files=True)
        directory = Action(kind="launch", launch_mode="file",
                           launch_target=str(self.root))
        with self.assertRaisesRegex(LaunchError, "not a file"):
            validate_launch(directory, check_files=True)

    def test_app_execute_permissions_and_windows_extension(self):
        with patch("macro_launch.os.access", return_value=False):
            with self.assertRaisesRegex(LaunchError, "not executable"):
                validate_launch(Action(kind="launch", launch_target=str(self.executable)),
                                check_files=True, platform_name="linux")
        txt_executable = Action(kind="launch", launch_target=str(self.document))
        with self.assertRaisesRegex(LaunchError, "exe"):
            validate_launch(txt_executable, check_files=True, platform_name="win32")

    def test_missing_file_or_permission_denial_never_dispatches(self):
        process = Mock()
        act = Action(kind="launch", launch_target=str(self.root / "missing.exe"))
        with self.assertRaises(LaunchError):
            launch_target(act, platform_name="win32", popen=process)
        process.assert_not_called()
        act = Action(kind="launch", launch_target=str(self.executable))
        process.side_effect = PermissionError(13, "Permission denied")
        with self.assertRaisesRegex(LaunchError, "Permission denied"):
            launch_target(act, platform_name="win32", popen=process)

    def test_file_and_url_reject_arguments_and_nul(self):
        for mode, value in (("file", str(self.document)),
                            ("url", "https://example.com")):
            with self.subTest(mode=mode), self.assertRaises(LaunchError):
                validate_launch(Action(kind="launch", launch_mode=mode,
                                       launch_target=value, launch_args="--flag"))
        with self.assertRaises(LaunchError):
            validate_launch(Action(kind="launch", launch_target=str(self.executable),
                                   launch_args="hello\x00world"))
        with self.assertRaises(ValueError):
            validate_action({"kind":"launch", "launch_target":5})

    def test_preflight_checks_only_enabled_reachable_actions(self):
        missing = Action(kind="launch", launch_target=str(self.root / "missing.exe"))
        actions = [Action(kind="wait",seconds=0), missing]
        findings = inspect_workflow(actions)
        self.assertTrue(any(x.index == 1 and x.severity == "error" for x in findings))
        actions[1] = Action(kind="launch", launch_target=str(self.root / "missing.exe"),
                            enabled=False)
        self.assertEqual(inspect_workflow(actions), [])
        actions[1] = missing
        self.assertEqual(inspect_workflow(actions, start_index=0)[0].index, 1)

    def test_runtime_respects_disabled_actions_and_target_binding(self):
        launched = []
        target = WindowInfo(123, "Target", "Test", 200, 2, 3, 400, 500)
        class FailWindowManager:
            def windows(self):
                raise AssertionError("Launch should never activate target")
        results = []
        with patch("macro_runtime.launch_target", side_effect=launched.append):
            MacroExecutor([
                Action(kind="launch", launch_target=str(self.executable), enabled=False),
                Action(kind="launch", launch_target=str(self.executable)),
            ], 1, 0, lambda *x:None, lambda *x:results.append(x),
            automation=FakeDesktop(), window_target=target_from_window(target),
            window_manager=FailWindowManager()).run()
        self.assertEqual(len(launched),1)
        self.assertTrue(results[0][0])

    def test_launch_only_run_does_not_import_screen_input_backend(self):
        results, dispatched = [], []
        runner = MacroExecutor([
            Action(kind="launch", launch_target=str(self.executable)),
            Action(kind="wait", seconds=0),
        ], 1, 0, lambda *args:None, lambda *args:results.append(args))
        with patch.object(runner, "_pag", side_effect=AssertionError(
                "No global input dependency for launch-only runs")), patch(
                    "macro_runtime.launch_target", side_effect=dispatched.append):
            runner.run()
        self.assertTrue(results[0][0], results)
        self.assertEqual(len(dispatched), 1)

    def test_launch_failure_skip_policy_keeps_next_action_and_no_double_launch(self):
        results, attempts, skipped = [], [], []
        actions = [
            Action(kind="launch", launch_target=str(self.executable),
                   failure_policy="skip"),
            Action(kind="wait", seconds=0),
        ]
        runner = MacroExecutor(
            actions, 1, 0, lambda *args:None, lambda *args:results.append(args),
            on_diagnostic=skipped.append)
        def denied(action):
            attempts.append(action.kind)
            raise LaunchError("Executable was not available")
        with patch("macro_runtime.launch_target", side_effect=denied):
            runner.run()
        self.assertTrue(results[0][0], results)
        self.assertEqual(attempts, ["launch"])
        self.assertTrue(any(x["event"] == "action_skipped" for x in skipped))

    def test_stop_before_dispatch_prevents_side_effects(self):
        launched, results = [], []
        runner = MacroExecutor([
            Action(kind="launch",launch_target=str(self.executable))],
            1, 0, lambda *x:None,lambda *x:results.append(x),
            automation=FakeDesktop())
        runner.stop()
        with patch("macro_runtime.launch_target", side_effect=launched.append):
            runner.run()
        self.assertEqual(launched,[])
        self.assertFalse(results[0][0])

    def test_step_pauses_before_launch(self):
        launched, finished = [], threading.Event()
        runner = MacroExecutor([
            Action(kind="launch", launch_target=str(self.executable))],
            1, 0, lambda *a:None, lambda *a:finished.set(),
            automation=FakeDesktop(), step_mode=True)
        with patch("macro_runtime.launch_target", side_effect=launched.append):
            runner.start()
            self.assertFalse(finished.wait(.05))
            self.assertEqual(launched,[])
            runner.step()
            self.assertTrue(finished.wait(2))
        self.assertEqual(len(launched),1)


if __name__ == "__main__":
    unittest.main()
