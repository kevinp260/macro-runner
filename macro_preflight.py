"""Pre-run checks for problems that action/schema validation cannot detect.

Only referenced image files are read. Screen limits are advisory because
secondary monitors and platform-specific scaling may extend the desktop.
This module does not capture screenshots or send mouse/keyboard input.
"""
import re
import sys
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from macro_flow import CONTROL, has_smart_actions, validate_flow, validate_start_selection
from macro_model import validate_action


@dataclass(frozen=True)
class PreflightFinding:
    severity: str  # "error" blocks execution; "warning" needs confirmation
    index: Optional[int]  # Zero-based original flat workflow index
    message: str


def _flow_error_index(message):
    match = re.search(r"action (\d+)", message, re.IGNORECASE)
    return int(match.group(1)) - 1 if match else None


def _inside_primary_screen(x, y, screen_size):
    width, height = screen_size
    return 0 <= x < width and 0 <= y < height


def _image_issues(action, index, findings, required):
    path = Path(action.image_path)
    severity = "error" if required else "warning"
    try:
        # A reference can exist but still be corrupt or unreadable.
        with Image.open(path) as image:
            dimensions = image.size
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError):
        findings.append(PreflightFinding(
            severity, index, "Reference image is missing or unreadable: "
            f"{action.image_path}. Choose an accessible image in Properties."))
        return
    if action.region_x is not None:
        if dimensions[0] > action.region_w or dimensions[1] > action.region_h:
            # An image larger than the search region can never match.
            image_severity = ("error" if required and action.match_mode == "matches"
                              else "warning")
            findings.append(PreflightFinding(
                image_severity, index,
                "Reference image is larger than its search region. "
                "Select a larger region or a smaller reference image."))


def _geometry_issues(action, index, screen_size, findings):
    if screen_size is None:
        return
    if (not isinstance(screen_size, (tuple, list)) or len(screen_size) != 2 or
            any(not isinstance(v, int) or isinstance(v, bool) or v <= 0
                for v in screen_size)):
        return

    points = []
    if action.kind in ("click", "move", "drag"):
        points.append(("Start", action.x, action.y))
    if action.kind == "drag":
        points.append(("Destination", action.to_x, action.to_y))
    if action.kind in ("if_start", "until_start", "wait_until") and action.condition_source == "pixel":
        points.append(("Pixel", action.pixel_x, action.pixel_y))
    for label, x, y in points:
        if not _inside_primary_screen(x, y, screen_size):
            findings.append(PreflightFinding(
                "warning", index,
                f"{label} coordinates ({x}, {y}) are outside the primary screen "
                f"({screen_size[0]}×{screen_size[1]}). Check the target display."))

    if (action.kind == "watch_start" or
            action.kind in ("click_image", "if_start", "until_start", "wait_until")
            and action.condition_source == "image"):
        if action.region_x is not None:
            x, y, width, height = (
                action.region_x, action.region_y, action.region_w, action.region_h)
            if (x < 0 or y < 0 or x + width > screen_size[0] or
                    y + height > screen_size[1]):
                findings.append(PreflightFinding(
                    "warning", index,
                    "Screen region extends outside the primary display. "
                    "Check its coordinates, monitors and display scaling."))


def inspect_workflow(actions, *, start_index=0, screen_size=None,
                     platform_name=None, session_type=None):
    """Return pre-run findings in workflow order, without performing actions.

    The same model and structural checks as MacroExecutor are applied first.
    Files and display bounds are checked only for actions reachable from the
    requested start position; disabled leaves are never executed.
    """
    findings = []
    if not actions:
        return [PreflightFinding("error", None, "The workflow has no actions.")]

    normalized = []
    invalid_actions = False
    for index, raw in enumerate(actions):
        try:
            values = asdict(raw) if is_dataclass(raw) else raw
            normalized.append(validate_action(values))
        except (TypeError, ValueError) as exc:
            invalid_actions = True
            findings.append(PreflightFinding(
                "error", index, f"Invalid action settings: {exc}"))
            normalized.append(None)

    if invalid_actions:
        return findings

    try:
        validate_flow(normalized)
    except ValueError as exc:
        findings.append(PreflightFinding(
            "error", _flow_error_index(str(exc)), f"Invalid workflow structure: {exc}"))
        return findings

    if isinstance(start_index, bool) or not isinstance(start_index, int) or not (
            0 <= start_index < len(normalized)):
        return [PreflightFinding(
            "error", None, "Selected start action is out of range.")]

    if has_smart_actions(normalized):
        try:
            validate_start_selection(normalized, start_index)
        except ValueError as exc:
            findings.append(PreflightFinding(
                "error", start_index, str(exc)))
            return findings

    if not any(a.enabled and a.kind not in CONTROL
               for a in normalized[start_index:]):
        findings.append(PreflightFinding(
            "error", start_index, "No enabled executable actions from this position."))

    desktop_actions = {"click", "move", "drag", "scroll", "key", "key_down",
                       "key_up", "click_image", "watch_start", "wait_until",
                       "if_start", "until_start"}
    active = normalized[start_index:]
    platform_name = platform_name if platform_name is not None else sys.platform
    if (platform_name.startswith("linux") and
            (session_type or "").lower() == "wayland" and
            any(a.enabled and a.kind in desktop_actions for a in active)):
        findings.append(PreflightFinding(
            "warning", None,
            "Wayland may restrict global input and screen capture. "
            "Use an X11 session where required; verify desktop permissions."))

    for index in range(start_index, len(normalized)):
        action = normalized[index]
        # Control markers are necessary for flow execution even though they
        # are not leaf actions. Disabled leaf actions never access the screen.
        required = action.enabled
        if (action.kind in ("click_image", "wait_until", "if_start", "until_start")
                and action.condition_source == "image"):
            # Disabled image actions have no runtime dependency on their file.
            if required:
                _image_issues(action, index, findings, required=True)
        if required:
            _geometry_issues(action, index, screen_size, findings)

    return findings
