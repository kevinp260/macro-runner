"""Offline OCR parsing, validation, model, preflight and playback tests."""
from dataclasses import asdict
import json
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image

from macro_model import Action, validate_action, serialize_document, parse_document
from macro_ocr import OCRError, TextMatch, find_text, match_tsv, check_engine
from macro_preflight import inspect_workflow
from macro_runtime import MacroExecutor

TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "5\t1\t1\t1\t1\t1\t10\t5\t35\t12\t96\tSign\n"
    "5\t1\t1\t1\t1\t2\t51\t5\t15\t12\t91\tIn\n"
    "5\t1\t1\t1\t2\t1\t10\t25\t35\t12\t99\tCancel\n"
)


class OCRCoreTests(unittest.TestCase):
    def test_case_insensitive_phrase_with_box_and_origin(self):
        match = match_tsv(TSV, "sign in", 200, 50, .9, origin=(100, 50))
        self.assertEqual(match, TextMatch(110, 55, 56, 12, .91))
        self.assertEqual(match.center, (138, 61))

    def test_ambiguous_text_blocks_optional_click(self):
        second = (
            "5\t1\t1\t1\t2\t2\t51\t25\t15\t12\t95\tIn\n"
        )
        duplicate = TSV + second.replace("2\t2\t51", "2\t1\t51")
        # A different OCR line containing the same phrase.
        duplicate += (
            "5\t1\t1\t1\t3\t1\t10\t40\t35\t12\t98\tSign\n"
            "5\t1\t1\t1\t3\t2\t51\t40\t15\t12\t97\tIn\n"
        )
        with self.assertRaisesRegex(OCRError, "multiple"):
            match_tsv(duplicate, "sign in", 200, 70, .8, require_unique=True)
        self.assertIsNotNone(match_tsv(duplicate, "sign in", 200, 70, .8))

    def test_threshold_and_missing_words(self):
        self.assertIsNone(match_tsv(TSV, "sign in", 200, 50, .95))
        self.assertIsNone(match_tsv(TSV, "sign out", 200, 50, .7))
        self.assertIsNone(match_tsv(TSV, "in cancel", 200, 50, .5))

    def test_bounding_boxes_outside_capture_are_ignored(self):
        self.assertIsNone(match_tsv(TSV, "sign in", 40, 20, .5))
        with self.assertRaisesRegex(OCRError, "bounding boxes"):
            match_tsv("garbage", "sign in", 100, 100, .5)

    def test_probe_uses_only_requested_region_and_no_files(self):
        action = Action(kind="find_text", text_target="sign in",
                        region_x=100, region_y=50, region_w=200, region_h=50)
        calls = []
        def screenshot(region=None):
            calls.append(region)
            return Image.new("RGB", (200, 50))
        with patch("macro_ocr._run", return_value=TSV.encode()) as command:
            result = find_text(action, screenshot, executable="local-tesseract")
        self.assertEqual(result.center, (138, 61))
        self.assertEqual(calls, [(100, 50, 200, 50)])
        args = command.call_args
        self.assertEqual(args.args[0][:3], ["local-tesseract", "stdin", "stdout"])
        self.assertIn(b"PNG", args.kwargs["image_bytes"][:10])

    def test_screenshot_dpi_mismatch_is_reported(self):
        action = Action(kind="find_text", text_target="sign",
                        region_x=0, region_y=0, region_w=100, region_h=30)
        with self.assertRaisesRegex(OCRError, "DPI scaling"):
            find_text(action, lambda region=None: Image.new("RGB", (50, 30)),
                      executable="tesseract")

    def test_engine_and_language_pack_errors(self):
        with patch("macro_ocr.engine_path", return_value="tesseract"), patch(
                "macro_ocr._run", return_value=b"List of available languages\neng\nfra\n"):
            self.assertEqual(check_engine("eng+fra"), "tesseract")
            with self.assertRaisesRegex(OCRError, "deu"):
                check_engine("eng+deu")
        with self.assertRaisesRegex(OCRError, "language"):
            check_engine("-psm")

    def test_subprocess_failure_is_sanitized(self):
        from macro_ocr import _run
        completed = MagicMock(returncode=1, stdout=b"",
                              stderr=b"SECRET OCR TEXT HERE")
        with patch("macro_ocr.subprocess.run", return_value=completed):
            with self.assertRaises(OCRError) as ctx:
                _run(["tesseract", "stdin", "stdout"])
        self.assertNotIn("SECRET", str(ctx.exception))

    def test_action_schema_validation_and_json_roundtrip(self):
        actions = [Action(kind="find_text", text_target="Sign In",
                          text_click=True, text_language="eng+deu",
                          text_confidence=.85),
                   Action(kind="wait_text", text_target="Ready",
                          timeout=2, poll_interval=.2)]
        stored = serialize_document(actions, 2, 0)
        recovered, settings = parse_document(json.loads(json.dumps(stored)))
        self.assertEqual(recovered, actions)
        self.assertEqual(settings["repeat_count"], 2)
        for wrong in (
            {"kind": "find_text", "text_confidence": 1.5},
            {"kind": "find_text", "text_language": "-eng"},
            {"kind": "wait_text", "text_click": True},
            {"kind": "find_text", "region_x": 0, "region_y": 0, "region_w": None},
            {"kind": "wait_text", "timeout": -1},
            {"kind": "find_text", "text_target": "bad\nline"},
            {"kind": "find_text", "failure_policy": "retry"},
        ):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                validate_action(wrong)
        self.assertIsNotNone(validate_action(asdict(
            Action(kind="wait_text", text_target="Ready", failure_policy="retry"))))

    def test_preflight_blocks_missing_backend_or_unconfigured_phrase(self):
        missing = Action(kind="find_text", text_target="")
        with patch("macro_preflight.check_ocr_engine",
                   side_effect=OCRError("Missing local Tesseract")):
            findings = inspect_workflow([missing])
        self.assertTrue(any("Enter a phrase" in f.message for f in findings))
        self.assertTrue(any("Missing local Tesseract" in f.message for f in findings))

    def test_preflight_does_not_require_ocr_for_normal_workflows(self):
        with patch("macro_preflight.check_ocr_engine") as engine:
            findings = inspect_workflow([Action(kind="wait")])
        engine.assert_not_called()
        self.assertFalse(any(f.severity == "error" for f in findings))


class FakeAutomation:
    def __init__(self):
        self.calls = []
    def screenshot(self, region=None):
        return Image.new("RGB", (100, 50))
    def size(self):
        return (800, 600)
    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))
    def keyDown(self, key):
        self.calls.append(("keyDown", key))
    def keyUp(self, key):
        self.calls.append(("keyUp", key))
    def press(self, key):
        self.calls.append(("press", key))


class OCRRuntimeTests(unittest.TestCase):
    def executor(self, action, automation, diagnostics=None):
        results = []
        runner = MacroExecutor(
            [action], 1, 0, lambda *a: None,
            lambda *a: results.append(a),
            automation=automation, on_diagnostic=(
                diagnostics if diagnostics is not None else []).append)
        return runner, results

    def test_find_text_readonly_does_not_click(self):
        fake = FakeAutomation()
        runner, results = self.executor(
            Action(kind="find_text", text_target="PRIVATE", text_click=False),
            fake)
        with patch("macro_runtime.check_ocr_engine", return_value="tesseract"), patch(
                "macro_runtime.ocr_find_text",
                return_value=TextMatch(20, 10, 40, 10, .98)):
            runner.run()
        self.assertTrue(results[0][0])
        self.assertEqual(fake.calls, [])

    def test_click_only_after_confident_match(self):
        fake = FakeAutomation()
        diagnostics = []
        runner, results = self.executor(
            Action(kind="find_text", text_target="PRIVATE", text_click=True),
            fake, diagnostics)
        with patch("macro_runtime.check_ocr_engine", return_value="tesseract"), patch(
                "macro_runtime.ocr_find_text",
                return_value=TextMatch(20, 10, 40, 10, .98)):
            runner.run()
        self.assertTrue(results[0][0])
        self.assertEqual(fake.calls, [("click", (40, 15), {})])
        self.assertNotIn("PRIVATE", json.dumps(diagnostics))

    def test_missing_phrase_blocks_click(self):
        fake = FakeAutomation()
        runner, results = self.executor(
            Action(kind="find_text", text_target="PRIVATE", text_click=True),
            fake)
        with patch("macro_runtime.check_ocr_engine", return_value="tesseract"), patch(
                "macro_runtime.ocr_find_text", return_value=None):
            runner.run()
        self.assertFalse(results[0][0])
        self.assertEqual(fake.calls, [])

    def test_wait_text_polls_without_click(self):
        fake = FakeAutomation()
        runner, results = self.executor(
            Action(kind="wait_text", text_target="ready",
                   timeout=.3, poll_interval=.1), fake)
        with patch("macro_runtime.check_ocr_engine", return_value="tesseract"), patch(
                "macro_runtime.ocr_find_text",
                side_effect=[None, TextMatch(20, 10, 40, 10, .98)]) as probe:
            runner.run()
        self.assertTrue(results[0][0])
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
