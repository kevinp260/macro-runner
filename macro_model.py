"""Serializable macro actions and validation (no GUI dependencies)."""
import math
from dataclasses import dataclass
from typing import List, Literal, Optional

ActionType = Literal["click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end"]

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

    if action.kind not in ("click", "wait", "key", "move", "scroll", "drag", "loop_start", "loop_end"):
        raise ValueError(f"Unknown action type: {action.kind!r}.")
    if not isinstance(action.name, str):
        raise ValueError("Action name must be text.")
    _positive_int(action.repeats, "Action repeats")
    if not isinstance(action.enabled, bool):
        raise ValueError("Enabled must be true or false.")
    if action.kind in ("loop_start", "loop_end"):
        # Loop markers control the sequence itself and cannot be disabled.
        if not action.enabled:
            raise ValueError("Loop markers must remain enabled.")
        if action.kind == "loop_end" and action.repeats != 1:
            raise ValueError("Loop End cannot have its own repeat count.")
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
    loop_spans(actions)
    return actions


DOCUMENT_VERSION = 2


def serialize_document(actions: List[Action], repeat_count: int, start_delay: float):
    """Create a full saved macro, including execution settings."""
    _positive_int(repeat_count, "Whole-sequence repeat count")
    _finite_nonnegative(start_delay, "Start delay")
    from dataclasses import asdict
    normalized = [validate_action(asdict(action)) for action in actions]
    loop_spans(normalized)
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
