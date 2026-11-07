"""Pre-run validator tests (no GUI, display or input required)."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from macro_model import Action, parse_document, serialize_document
from macro_preflight import inspect_workflow


class PreflightTests(unittest.TestCase):
    def test_valid_workflow_and_legacy_document_have_no_findings(self):
        actions = [Action(kind="wait", seconds=0), Action(kind="click", x=10, y=20)]
        self.assertEqual(inspect_workflow(actions, screen_size=(1920, 1080)), [])
        legacy, _ = parse_document([{"kind": "wait"}])
        self.assertEqual(inspect_workflow(legacy), [])
        saved, _ = parse_document(serialize_document(actions, 1, 0))
        self.assertEqual(inspect_workflow(saved, screen_size=(1920, 1080)), [])

    def test_invalid_settings_and_flow_are_blocking_with_action_indices(self):
        findings = inspect_workflow([Action(kind="click", x=None, y=0)])
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].index, 0)
        self.assertIn("x", findings[0].message)
        findings = inspect_workflow([Action(kind="if_start", condition_source="pixel"),
                                     Action(kind="wait")])
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].index, 0)
        self.assertIn("structure", findings[0].message)
        self.assertEqual(inspect_workflow([])[0].severity, "error")

    def test_no_enabled_executables_blocks(self):
        findings = inspect_workflow([Action(kind="wait", enabled=False)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "error")
        self.assertIn("No enabled", findings[0].message)

    def test_unavailable_and_corrupted_reference_images(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.png"
            corrupt = Path(temp) / "corrupt.png"
            corrupt.write_text("not a PNG", encoding="utf-8")
            for path in (missing, corrupt):
                with self.subTest(path=path):
                    findings = inspect_workflow([
                        Action(kind="click_image", image_path=str(path))])
                    self.assertEqual([(f.severity, f.index)
                                      for f in findings], [("error", 0)])
                    self.assertIn("unreadable", findings[0].message)

    def test_reference_image_region_is_validated_without_screen_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reference.png"
            Image.new("RGB", (50, 40)).save(path)
            action = Action(kind="click_image", image_path=str(path),
                            region_x=0, region_y=0, region_w=20, region_h=20)
            issues = inspect_workflow([action])
            self.assertEqual([f.severity for f in issues], ["error"])
            self.assertIn("larger", issues[0].message)
            action.region_w = 100
            action.region_h = 100
            self.assertEqual(inspect_workflow([action], screen_size=(200, 200)), [])
            action.region_x = 180
            issues = inspect_workflow([action], screen_size=(200, 200))
            self.assertEqual([f.severity for f in issues], ["warning"])
            self.assertIn("primary", issues[0].message)

    def test_negative_and_offscreen_points_are_advisory(self):
        actions = [Action(kind="click", x=-100, y=15),
                   Action(kind="drag", x=10, y=10, to_x=2000, to_y=20),
                   Action(kind="if_start", condition_source="pixel",
                          pixel_x=1500, pixel_y=2),
                   Action(kind="wait"),
                   Action(kind="if_end"),
                   Action(kind="watch_start", region_x=900, region_y=5,
                          region_w=400, region_h=30),
                   Action(kind="wait"),
                   Action(kind="watch_end")]
        issues = inspect_workflow(actions, screen_size=(1024, 768))
        self.assertEqual(len(issues), 4)
        self.assertTrue(all(f.severity == "warning" for f in issues))
        self.assertEqual([f.index for f in issues], [0, 1, 2, 5])

    def test_wayland_restrictions_are_warned_once_not_blocked(self):
        actions = [Action(kind="click", x=1, y=1), Action(kind="key", keys="enter")]
        issues = inspect_workflow(actions, platform_name="linux", session_type="wayland")
        self.assertEqual(len(issues), 1)
        self.assertIn("Wayland", issues[0].message)
        self.assertEqual(issues[0].index, None)
        self.assertEqual(inspect_workflow(
            [Action(kind="wait")], platform_name="linux", session_type="wayland"), [])
        self.assertEqual(inspect_workflow(
            actions, platform_name="win32", session_type="wayland"), [])

    def test_disabled_and_preceding_images_are_not_required(self):
        actions = [Action(kind="click_image", image_path="/missing/example.png",
                          enabled=False),
                   Action(kind="wait")]
        self.assertEqual(inspect_workflow(actions), [])
        actions[0].enabled = True
        self.assertEqual(inspect_workflow(actions, start_index=1), [])
        self.assertEqual(inspect_workflow(actions, start_index=0)[0].severity, "error")

    def test_selected_run_reuses_control_flow_restrictions(self):
        actions = [Action(kind="if_start", condition_source="pixel"),
                   Action(kind="wait"), Action(kind="if_end"),
                   Action(kind="wait")]
        findings = inspect_workflow(actions, start_index=1)
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].index, 1)
        self.assertIn("inside a control block", findings[0].message)
        self.assertEqual(inspect_workflow(actions, start_index=3), [])
        self.assertEqual(inspect_workflow(actions, start_index=99)[0].severity, "error")


if __name__ == "__main__":
    unittest.main()
