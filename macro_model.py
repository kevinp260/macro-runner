"""Serializable macro actions and validation (no GUI dependencies)."""
import math
from dataclasses import dataclass
from typing import List, Literal, Optional

ActionType = Literal["click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end", "click_image", "wait_until", "if_start", "else", "if_end", "until_start", "until_end", "key_down", "key_up", "watch_start", "watch_end", "clipboard_set", "clipboard_paste", "launch", "wait_window"]

@dataclass
class Action:
    kind: ActionType
    name: str = ""
    repeats: int = 1
    enabled: bool = True
    # A failed leaf action stops by default. Retry is restricted to
    # condition/image polling (before any mouse/keyboard side effect).
    failure_policy: str = "stop"
    retry_count: int = 2       # Extra attempts after the first one (max 10).
    retry_delay: float = 1.0  # Seconds between attempts.
    x: Optional[int] = None
    y: Optional[int] = None
    button: str = "left"
    clicks: int = 1
    interval: float = 0.0
    seconds: float = 1.0
    key_mode: str = "press"
    keys: str = "enter"
    move_duration: float = 0.2
    to_x: Optional[int] = None
    to_y: Optional[int] = None
    scroll_amount: int = -3
    # Shared condition for Click Image, Wait Until, If and Repeat Until.
    condition_source: str = "image"
    match_mode: str = "matches"
    image_path: str = ""
    confidence: float = 0.9
    region_x: Optional[int] = None
    region_y: Optional[int] = None
    region_w: Optional[int] = None
    region_h: Optional[int] = None
    pixel_x: int = 0
    pixel_y: int = 0
    pixel_color: str = "#00FF00"
    pixel_tolerance: int = 10
    timeout: float = 10.0
    poll_interval: float = 0.3
    # Watch region: 0 means keep watching until Stop.
    watch_max_changes: int = 0
    watch_change_percent: float = 5.0
    watch_pixel_tolerance: int = 15
    watch_confirmations: int = 2
    # Clipboard text is saved in local workflow JSON and must never be logged.
    # None for clipboard_paste means use existing system clipboard text.
    clipboard_text: Optional[str] = None
    clipboard_restore: bool = True
    # Launch modes: application (direct executable), file (default app),
    # url (OS browser). One literal argv argument per launch_args line.
    launch_mode: str = "application"
    launch_target: str = ""
    launch_args: str = ""
    # Wait for window: optionally reuse workflow target or a picked/title match.
    window_wait_source: str = "custom"
    window_wait_state: str = "appears"
    window_wait_title: str = ""
    window_wait_class: str = ""
    window_wait_handle: int = 0
    window_wait_pid: int = 0


def _finite_nonnegative(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number.")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be finite and nonnegative.")


def _positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer.")


def validate_action(item):
    """Validate a loaded or newly constructed action, preserving the legacy JSON format."""
    if not isinstance(item, dict):
        raise ValueError("Every action must be an object.")
    try:
        action = Action(**item)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid action fields: {exc}") from exc

    if action.kind not in ("click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end", "click_image", "wait_until", "if_start", "else", "if_end", "until_start", "until_end", "key_down", "key_up", "watch_start", "watch_end", "clipboard_set", "clipboard_paste", "launch", "wait_window"):
        raise ValueError(f"Unknown action type: {action.kind!r}.")
    if not isinstance(action.name, str):
        raise ValueError("Action name must be text.")
    _positive_int(action.repeats, "Action repeats")
    if not isinstance(action.enabled, bool):
        raise ValueError("Enabled must be true or false.")
    if action.failure_policy not in ("stop", "skip", "retry"):
        raise ValueError("On failure must be Stop workflow, Skip action, or Retry.")
    if (isinstance(action.retry_count, bool) or
            not isinstance(action.retry_count, int) or
            not 0 <= action.retry_count <= 10):
        raise ValueError("Extra retry attempts must be an integer from 0 to 10.")
    _finite_nonnegative(action.retry_delay, "Retry delay")
    if action.retry_delay > 60:
        raise ValueError("Retry delay must be 0–60 seconds.")
    if action.failure_policy == "retry":
        if action.kind not in ("click_image", "wait_until"):
            raise ValueError(
                "Retry is supported only for Click Image and Wait Until. "
                "Other actions may have already sent mouse/keyboard input.")
        if action.retry_count < 1:
            raise ValueError("Retry needs at least one extra attempt.")
    markers = ("loop_start", "loop_end", "if_start", "else", "if_end",
               "until_start", "until_end", "watch_start", "watch_end")
    if action.kind in markers:
        if action.failure_policy != "stop":
            raise ValueError("Failure handling applies only to executable actions.")
        if not action.enabled:
            raise ValueError("Control markers must remain enabled.")
        if action.kind not in ("loop_start", "until_start") and action.repeats != 1:
            raise ValueError("Only block starts can have a repeat count.")
    if action.kind == "watch_start":
        region = (action.region_x, action.region_y, action.region_w, action.region_h)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in region):
            raise ValueError("Watch region needs integer X, Y, width and height. Use Draw region.")
        if action.region_x < 0 or action.region_y < 0:
            # PyAutoGUI screenshot(region=...) does not support negative origins
            # consistently across operating systems.
            raise ValueError("Watch region must use nonnegative screen coordinates.")
        if not 1 <= action.region_w <= 10000 or not 1 <= action.region_h <= 10000:
            raise ValueError("Watch region width and height must be 1–10000 pixels.")
        _finite_nonnegative(action.poll_interval, "Watch polling interval")
        if not 0.1 <= action.poll_interval <= 60:
            raise ValueError("Watch polling interval must be 0.1–60 seconds.")
        _finite_nonnegative(action.watch_change_percent, "Changed pixels percentage")
        if not 0 < action.watch_change_percent <= 100:
            raise ValueError("Changed pixels percentage must be greater than 0 and at most 100.")
        if (isinstance(action.watch_pixel_tolerance, bool) or
            not isinstance(action.watch_pixel_tolerance, int) or
            not 0 <= action.watch_pixel_tolerance <= 255):
            raise ValueError("Pixel tolerance must be an integer from 0 to 255.")
        if (isinstance(action.watch_confirmations, bool) or
            not isinstance(action.watch_confirmations, int) or
            not 1 <= action.watch_confirmations <= 10):
            raise ValueError("Confirmations must be an integer from 1 to 10.")
        if (isinstance(action.watch_max_changes, bool) or
            not isinstance(action.watch_max_changes, int) or
            not 0 <= action.watch_max_changes <= 1000000):
            raise ValueError("Maximum changes must be 0 (unlimited) to 1000000.")
    if action.kind in ("click_image", "wait_until", "if_start", "until_start"):
        if action.condition_source not in ("image", "pixel"):
            raise ValueError("Condition source must be image or pixel.")
        if action.match_mode not in ("matches", "not_matches"):
            raise ValueError("Condition test must be matches or not_matches.")
        if action.kind == "click_image" and (
            action.condition_source != "image" or action.match_mode != "matches"
        ):
            raise ValueError("Click Image requires an image match.")
        if action.kind == "click_image" and action.button not in ("left", "right", "middle"):
            raise ValueError("Invalid image-click mouse button.")
        if action.condition_source == "image":
            if not isinstance(action.image_path, str) or not action.image_path.strip():
                raise ValueError("Select a reference image.")
            _finite_nonnegative(action.confidence, "Image confidence")
            if not 0 < action.confidence <= 1:
                raise ValueError("Image confidence must be greater than 0 and at most 1.")
            region = (action.region_x, action.region_y, action.region_w, action.region_h)
            if any(v is not None for v in region):
                if any(isinstance(v, bool) or not isinstance(v, int) for v in region):
                    raise ValueError("Image region requires four integers (x, y, w, h).")
                if action.region_w < 1 or action.region_h < 1:
                    raise ValueError("Image region width and height must be positive.")
        else:
            for field in ("pixel_x", "pixel_y"):
                value = getattr(action, field)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"{field} must be an integer.")
            if (not isinstance(action.pixel_color, str) or
                len(action.pixel_color) != 7 or action.pixel_color[0] != "#" or
                any(c not in "0123456789abcdefABCDEF" for c in action.pixel_color[1:])):
                raise ValueError("Pixel color must be #RRGGBB.")
            if (isinstance(action.pixel_tolerance, bool) or
                not isinstance(action.pixel_tolerance, int) or
                not 0 <= action.pixel_tolerance <= 255):
                raise ValueError("Pixel tolerance must be 0 to 255.")
        _finite_nonnegative(action.poll_interval, "Poll interval")
        if action.poll_interval <= 0:
            raise ValueError("Poll interval must be positive.")
        if action.kind in ("click_image", "wait_until"):
            _finite_nonnegative(action.timeout, "Timeout")
    if action.kind == "wait_window":
        from macro_window_wait import validate_window_wait
        validate_window_wait(action)
        # Reuse existing timeout/poll_interval fields for UI and persistence.
    if action.kind == "launch":
        from macro_launch import validate_launch
        if (action.launch_mode not in ("application", "file", "url") or
                not isinstance(action.launch_target, str) or
                not isinstance(action.launch_args, str)):
            raise ValueError("Invalid launch mode, path/URL or argument text.")
        # An unconfigured leaf is editable/savable, but cannot execute.
        # Preflight always blocks empty or nonexistent targets.
        if action.launch_target:
            validate_launch(action)
        elif action.launch_args and ("\x00" in action.launch_args or
                                      "\r" in action.launch_args):
            raise ValueError("Launch arguments contain invalid control characters.")
    if action.kind in ("clipboard_set", "clipboard_paste"):
        if action.kind == "clipboard_set" and not isinstance(action.clipboard_text, str):
            raise ValueError("Set clipboard requires text (empty text clears it).")
        if action.clipboard_text is not None and not isinstance(action.clipboard_text, str):
            raise ValueError("Clipboard text must be a string.")
        if not isinstance(action.clipboard_restore, bool):
            raise ValueError("Restore clipboard must be true or false.")
    if action.kind in ("click", "move", "drag"):
        for field, value in (("x", action.x), ("y", action.y)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field} must be an integer.")
    if action.kind == "drag":
        for field, value in (("to_x", action.to_x), ("to_y", action.to_y)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{field} must be an integer.")
        _finite_nonnegative(action.move_duration, "Drag duration")
        if action.button not in ("left", "right", "middle"):
            raise ValueError("Invalid drag button.")
    if action.kind == "scroll":
        if isinstance(action.scroll_amount, bool) or not isinstance(action.scroll_amount, int):
            raise ValueError("Scroll steps must be an integer.")
        if action.scroll_amount == 0:
            raise ValueError("Scroll steps cannot be zero.")
    if action.kind == "click":
        if action.button not in ("left", "right", "middle"):
            raise ValueError("Invalid mouse button.")
        _positive_int(action.clicks, "Click count")
        _finite_nonnegative(action.interval, "Click interval")
    elif action.kind == "wait":
        _finite_nonnegative(action.seconds, "Wait duration")
    elif action.kind == "move":
        _finite_nonnegative(action.move_duration, "Move duration")
    elif action.kind == "key":
        if action.key_mode not in ("press", "type") or not isinstance(action.keys, str) or not action.keys.strip():
            raise ValueError("Invalid key mode or empty key/text.")
    elif action.kind in ("key_down", "key_up"):
        from macro_keys import valid_hold_key
        if not valid_hold_key(action.keys):
            raise ValueError("Hold/Release requires one supported key name, not a combination.")
        if action.repeats != 1:
            raise ValueError("Hold/Release repeat count must be 1.")
    return action


def loop_spans(actions: List[Action]):
    """Map Loop Start indices to matching Loop End indices; one level only."""
    starts = {}
    open_index = None
    for index, action in enumerate(actions):
        if action.kind == "loop_start":
            if open_index is not None:
                raise ValueError(f"Nested loops are not supported (action {index + 1}).")
            open_index = index
        elif action.kind == "loop_end":
            if open_index is None:
                raise ValueError(f"Loop End at action {index + 1} has no Loop Start.")
            if index == open_index + 1:
                raise ValueError(f"Loop at action {open_index + 1} is empty.")
            starts[open_index] = index
            open_index = None
    if open_index is not None:
        raise ValueError(f"Loop Start at action {open_index + 1} has no Loop End.")
    return starts


def parse_sequence(data) -> List[Action]:
    if not isinstance(data, list):
        raise ValueError("The sequence must be a JSON array of actions.")
    actions = [validate_action(action) for action in data]
    from macro_flow import validate_flow
    validate_flow(actions)
    return actions


DOCUMENT_VERSION = 2


def serialize_document(actions: List[Action], repeat_count: int, start_delay: float,
                       window_target=None):
    """Create a full saved macro, including execution settings."""
    _positive_int(repeat_count, "Whole-sequence repeat count")
    _finite_nonnegative(start_delay, "Start delay")
    from dataclasses import asdict
    normalized = [validate_action(asdict(action)) for action in actions]
    from macro_flow import validate_flow
    validate_flow(normalized)
    validated = [asdict(action) for action in normalized]
    settings = {"repeat_count": repeat_count, "start_delay": start_delay}
    if window_target is not None:
        from macro_windows import validate_target
        settings["window_target"] = validate_target(window_target)
    return {
        "version": DOCUMENT_VERSION,
        "settings": settings,
        "actions": validated,
    }


def parse_document(data):
    """Return (actions, settings); legacy JSON action lists have settings=None."""
    if isinstance(data, list):
        return parse_sequence(data), None
    if not isinstance(data, dict) or data.get("version") != DOCUMENT_VERSION:
        raise ValueError("Unknown macro file format or version.")

    settings = data.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("Macro settings must be an object.")
    repeat_count = settings.get("repeat_count")
    start_delay = settings.get("start_delay")
    _positive_int(repeat_count, "Whole-sequence repeat count")
    _finite_nonnegative(start_delay, "Start delay")
    actions = parse_sequence(data.get("actions"))
    result = {"repeat_count": repeat_count, "start_delay": start_delay}
    if "window_target" in settings:
        from macro_windows import validate_target
        result["window_target"] = validate_target(settings["window_target"])
    return actions, result
