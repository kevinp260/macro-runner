"""Serializable macro actions and validation (no GUI dependencies)."""
import math
from dataclasses import dataclass
from typing import List, Literal, Optional

ActionType = Literal["click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end", "click_image", "wait_until", "if_start", "else", "if_end", "until_start", "until_end", "key_down", "key_up"]

@dataclass
class Action:
    kind: ActionType
    name: str = ""
    repeats: int = 1
    enabled: bool = True
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

    if action.kind not in ("click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end", "click_image", "wait_until", "if_start", "else", "if_end", "until_start", "until_end", "key_down", "key_up"):
        raise ValueError(f"Unknown action type: {action.kind!r}.")
    if not isinstance(action.name, str):
        raise ValueError("Action name must be text.")
    _positive_int(action.repeats, "Action repeats")
    if not isinstance(action.enabled, bool):
        raise ValueError("Enabled must be true or false.")
    markers = ("loop_start", "loop_end", "if_start", "else", "if_end",
               "until_start", "until_end")
    if action.kind in markers:
        if not action.enabled:
            raise ValueError("Control markers must remain enabled.")
        if action.kind not in ("loop_start", "until_start") and action.repeats != 1:
            raise ValueError("Only block starts can have a repeat count.")
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


def serialize_document(actions: List[Action], repeat_count: int, start_delay: float):
    """Create a full saved macro, including execution settings."""
    _positive_int(repeat_count, "Whole-sequence repeat count")
    _finite_nonnegative(start_delay, "Start delay")
    from dataclasses import asdict
    normalized = [validate_action(asdict(action)) for action in actions]
    from macro_flow import validate_flow
    validate_flow(normalized)
    validated = [asdict(action) for action in normalized]
    return {
        "version": DOCUMENT_VERSION,
        "settings": {"repeat_count": repeat_count, "start_delay": start_delay},
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
    return actions, {"repeat_count": repeat_count, "start_delay": start_delay}
