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
from macro_launch import LaunchError, validate_launch
from macro_files import FILE_KINDS, validate_file_action
from macro_variables import validate_references, unset_warnings
from macro_windows import WindowBinding, WindowManager, WindowUnavailable
from macro_ocr import check_engine as check_ocr_engine, OCRError


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

    if action.kind == "click_image" and (
            action.image_offset_x or action.image_offset_y):
        # The match center is not known until runtime. Flag only offsets
        # guaranteed to exceed the primary screen for every possible
        # center within the configured region (or entire primary screen).
        if action.region_x is None:
            bounds = (0, 0, screen_size[0], screen_size[1])
        else:
            bounds = (action.region_x, action.region_y,
                      action.region_w, action.region_h)
        bx, by, bw, bh = bounds
        x1, x2 = bx + action.image_offset_x, bx + bw - 1 + action.image_offset_x
        y1, y2 = by + action.image_offset_y, by + bh - 1 + action.image_offset_y
        if x2 < 0 or y2 < 0 or x1 >= screen_size[0] or y1 >= screen_size[1]:
            findings.append(PreflightFinding(
                "warning", index,
                "Image click offset cannot land on the primary screen from "
                "the current search area. Check offsets, other monitors "
                "and display scaling; runtime will block unsafe clicks."))

    if (action.kind in ("watch_start", "find_text", "wait_text") or
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
                     platform_name=None, session_type=None, window_target=None,
                     window_manager=None, variables=None, variable_overrides=None):
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

    try:
        definitions = validate_references(
            normalized, variables or [], require_outputs=True)
        for index, message in unset_warnings(
                normalized, definitions, start_index, variable_overrides):
            findings.append(PreflightFinding("warning", index, message))
    except ValueError as exc:
        findings.append(PreflightFinding(
            "error", None, f"Invalid variable settings: {exc}"))
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
                       "if_start", "until_start", "clipboard_paste",
                       "find_text", "wait_text"}
    active = normalized[start_index:]
    platform_name = platform_name if platform_name is not None else sys.platform
    if (platform_name.startswith("linux") and
            (session_type or "").lower() == "wayland" and
            any(a.enabled and a.kind in desktop_actions for a in active)):
        findings.append(PreflightFinding(
            "warning", None,
            "Wayland may restrict global input and screen capture. "
            "Use an X11 session where required; verify desktop permissions."))

    # Window waits are read-only checks; they do not require their window
    # to exist when a workflow starts. Verify the backend is available
    # without activating anything, and validate the selected source.
    wait_indices = [
        index for index in range(start_index, len(normalized))
        if normalized[index].enabled and normalized[index].kind == "wait_window"
    ]
    manager = window_manager
    if wait_indices:
        try:
            manager = manager or WindowManager()
            manager.all_windows()
        except (WindowUnavailable, OSError) as exc:
            findings.append(PreflightFinding("error", wait_indices[0], str(exc)))
            return findings
        for index in wait_indices:
            action = normalized[index]
            if action.window_wait_source == "workflow" and window_target is None:
                findings.append(PreflightFinding(
                    "error", index,
                    "Window wait uses the workflow target, but no target is configured."))
            elif (action.window_wait_source == "custom" and
                  not action.window_wait_title.strip()):
                findings.append(PreflightFinding(
                    "error", index, "Choose a window or enter its exact title."))
    if any(f.severity == "error" for f in findings):
        return findings

    binding = None
    target_info = None
    if window_target is not None:
        try:
            binding = WindowBinding(window_target, manager=manager)
            # No activation: a workflow may first launch a missing window
            # and then wait for it before performing bound input.
            target_info = binding.resolve()
        except WindowUnavailable as exc:
            if not str(exc).startswith("Target window was not found."):
                findings.append(PreflightFinding("error", None, str(exc)))
                return findings
            binding_consumers = {
                "click", "click_image", "move", "scroll", "drag",
                "key", "key_down", "key_up", "clipboard_paste",
                "wait_until", "if_start", "until_start", "watch_start",
                "find_text", "wait_text",
            }
            first_bound = next((
                index for index in range(start_index, len(normalized))
                if normalized[index].enabled and
                normalized[index].kind in binding_consumers
            ), len(normalized))
            earlier_wait = any(
                index < first_bound and normalized[index].window_wait_source == "workflow"
                and normalized[index].window_wait_state == "appears"
                for index in wait_indices
            )
            if not earlier_wait and first_bound < len(normalized):
                findings.append(PreflightFinding("error", None, str(exc)))
                return findings
            if first_bound < len(normalized):
                findings.append(PreflightFinding(
                    "warning", first_bound,
                    "The target window is not open yet. Client coordinates "
                    "will be verified when it appears, before input."))
        except (ValueError, OSError) as exc:
            findings.append(PreflightFinding("error", None, str(exc)))
            return findings

    checked_ocr_languages = set()
    for index in range(start_index, len(normalized)):
        action = normalized[index]
        # Control markers are necessary for flow execution even though they
        # are not leaf actions. Disabled leaf actions never access the screen.
        required = action.enabled
        if required and action.kind in ("find_text", "wait_text"):
            if not action.text_target.strip():
                findings.append(PreflightFinding(
                    "error", index, "Enter a phrase for local OCR text recognition."))
            if action.text_language not in checked_ocr_languages:
                checked_ocr_languages.add(action.text_language)
                try:
                    check_ocr_engine(action.text_language)
                except OCRError as exc:
                    findings.append(PreflightFinding("error", index, str(exc)))
        if required and action.kind == "launch" and (
                "launch_target" not in action.bindings):
            try:
                validate_launch(action, check_files=True, platform_name=platform_name)
            except LaunchError as exc:
                findings.append(PreflightFinding("error", index, str(exc)))
        if required and action.kind in FILE_KINDS:
            # Runtime resolves bound paths, including values from an earlier
            # action result; the editor can only check literal paths here.
            bound_paths = any(field in action.bindings
                              for field in ("file_path", "file_destination"))
            try:
                src, dest = validate_file_action(
                    action, require_paths=not bound_paths)
            except ValueError as exc:
                findings.append(PreflightFinding("error", index, str(exc)))
            else:
                for field, value in (("file_path", src),
                                     ("file_destination", dest)):
                    if (field == "file_destination" and
                            action.kind not in ("file_copy", "file_move")):
                        continue
                    if field not in action.bindings and value is None:
                        findings.append(PreflightFinding(
                            "error", index, f"Choose a {field.replace('_', ' ')} "
                            "or bind a typed text variable."))
                # Paths may be produced by earlier steps. Filesystem absence
                # is advisory; inaccessible drives return a useful warning.
                try:
                    if (not bound_paths
                            and action.kind in ("file_check", "file_copy", "file_move")
                            and not src.is_file()):
                        findings.append(PreflightFinding(
                            "warning", index,
                            "Source file is not present yet. Ensure an earlier "
                            "step creates it, or verify the selected file path."))
                    if (not bound_paths
                            and action.kind in ("file_copy", "file_move")
                            and (dest.exists() or dest.is_symlink())
                            and not action.file_overwrite):
                        findings.append(PreflightFinding(
                            "warning", index,
                            "Destination file already exists. Copy/Move refuses "
                            "to overwrite unless explicitly enabled."))
                except OSError as exc:
                    findings.append(PreflightFinding(
                        "warning", index,
                        "Cannot check the configured file path. Verify the "
                        "drive is available and the directory is accessible."))
        if (action.kind in ("click_image", "wait_until", "if_start", "until_start")
                and action.condition_source == "image"):
            # Disabled image actions have no runtime dependency on their file.
            if required and "image_path" not in action.bindings:
                _image_issues(action, index, findings, required=True)
        if required and binding is not None and binding.spec["relative"] and (
                target_info is not None):
            try:
                bound = binding.transform(action, target_info)
                if (action.kind in ("click_image", "wait_until", "if_start",
                                    "until_start", "watch_start", "find_text", "wait_text") and
                        (action.kind in ("watch_start", "find_text", "wait_text") or
                         action.condition_source == "image") and
                        bound.region_x is not None and
                        (bound.region_x < 0 or bound.region_y < 0)):
                    raise WindowUnavailable(
                        "Window screenshot region has a negative screen origin; "
                        "move the window onto a positive-coordinate display.")
                if (action.kind in ("wait_until", "if_start", "until_start") and
                        action.condition_source == "pixel" and
                        (bound.pixel_x < 0 or bound.pixel_y < 0)):
                    raise WindowUnavailable(
                        "Window pixel has a negative screen origin unsupported by "
                        "the screenshot backend.")
            except WindowUnavailable as exc:
                findings.append(PreflightFinding("error", index, str(exc)))
        elif required and not (binding is not None and
                               binding.spec["relative"] and target_info is None):
            _geometry_issues(action, index, screen_size, findings)

    return findings
