"""Typed workflow-scoped variables; no expressions, eval, or implicit coercion.

Defaults live in the document; overrides belong to one editor session and
are not serialized. Each whole-workflow repeat resets to defaults/overrides.
"""
from dataclasses import replace
import math
import re

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
TYPES = ("text", "number", "boolean", "coordinates")
MISSING = object()

# Only explicitly supported action fields can read variables. A coordinate
# binding supplies both coordinates atomically; it cannot mix with a stale X/Y.
BINDABLE = {
    "click": {"point": "coordinates"},
    "move": {"point": "coordinates"},
    "drag": {"point": "coordinates", "to_point": "coordinates"},
    "scroll": {"scroll_amount": "number"},
    "wait": {"seconds": "number"},
    "key": {"keys": "text"},
    "key_down": {"keys": "text"},
    "key_up": {"keys": "text"},
    "click_image": {"image_path": "text", "confidence": "number",
                    "image_offset_x": "number", "image_offset_y": "number"},
    "wait_until": {"image_path": "text", "confidence": "number",
                   "pixel_x": "number", "pixel_y": "number",
                   "pixel_color": "text", "timeout": "number"},
    "if_start": {"image_path": "text", "confidence": "number",
                 "pixel_x": "number", "pixel_y": "number",
                 "pixel_color": "text"},
    "until_start": {"image_path": "text", "confidence": "number",
                    "pixel_x": "number", "pixel_y": "number",
                    "pixel_color": "text"},
    "clipboard_set": {"clipboard_text": "text"},
    "clipboard_paste": {"clipboard_text": "text",
                        "clipboard_restore": "boolean"},
    "launch": {"launch_target": "text", "launch_args": "text"},
    "wait_window": {"window_wait_title": "text"},
    "file_check": {"file_path": "text"},
    "file_wait": {"file_path": "text"},
    "file_copy": {"file_path": "text", "file_destination": "text",
                  "file_overwrite": "boolean"},
    "file_move": {"file_path": "text", "file_destination": "text",
                  "file_overwrite": "boolean"},
    "folder_create": {"file_path": "text"},
}


def valid_name(name):
    return isinstance(name, str) and NAME.fullmatch(name) is not None


def _type_value(value, kind):
    if value is None:
        return None
    if kind == "text" and isinstance(value, str):
        return value
    if kind == "boolean" and type(value) is bool:
        return value
    if kind == "number" and type(value) in (int, float) and math.isfinite(value):
        return value
    if (kind == "coordinates" and isinstance(value, (list, tuple))
            and len(value) == 2 and all(type(n) is int for n in value)):
        return [value[0], value[1]]
    raise ValueError(f"Variable default/override must match its declared {kind} type.")


def validate_variables(definitions):
    if not isinstance(definitions, list) or len(definitions) > 100:
        raise ValueError("Workflow variables must be a list of at most 100 definitions.")
    result = []
    seen = set()
    for item in definitions:
        if (not isinstance(item, dict) or set(item) !=
                {"name", "type", "default"}):
            raise ValueError("Variable definitions need name, type and default.")
        name, kind = item["name"], item["type"]
        if not valid_name(name):
            raise ValueError("Variable names must be 1–64 ASCII letters, digits "
                             "or underscores, starting with a letter/underscore.")
        if name in seen:
            raise ValueError(f"Duplicate variable name: {name}")
        if kind not in TYPES:
            raise ValueError(f"Unknown variable type for {name}.")
        value = _type_value(item["default"], kind)
        result.append({"name": name, "type": kind, "default": value})
        seen.add(name)
    return result


def validate_action_variables(action):
    if not isinstance(action.bindings, dict):
        raise ValueError("Action variable bindings must be an object.")
    allowed = BINDABLE.get(action.kind, {})
    for field, name in action.bindings.items():
        if not isinstance(field, str) or field not in allowed:
            raise ValueError(f"Variable bindings are not supported for {action.kind}: {field!r}.")
        if not valid_name(name):
            raise ValueError("Action binding must use a valid variable name.")
    if not isinstance(action.result_variable, str) or (
            action.result_variable and not valid_name(action.result_variable)):
        raise ValueError("Result variable must be a valid variable name.")
    if action.result_variable and action.kind not in ("click_image", "clipboard_read"):
        raise ValueError("Only image clicks and clipboard reads produce variable results.")


def validate_references(actions, definitions, *, require_outputs=False):
    """Check all binding/result types; runtime also requires output targets."""
    definitions = validate_variables(definitions)
    types = {item["name"]: item["type"] for item in definitions}
    for index, action in enumerate(actions):
        for field, name in action.bindings.items():
            expected = BINDABLE[action.kind][field]
            if name not in types:
                raise ValueError(f"Action {index + 1}: undefined variable {name}.")
            if types[name] != expected:
                raise ValueError(
                    f"Action {index + 1}: {field} expects {expected}, "
                    f"but {name} is {types[name]}.")
        if require_outputs and action.kind == "clipboard_read" and not action.result_variable:
            raise ValueError(
                f"Action {index + 1}: choose a text result variable for Read clipboard.")
        if action.result_variable:
            expected = ("coordinates" if action.kind == "click_image" else "text")
            if action.result_variable not in types:
                raise ValueError(
                    f"Action {index + 1}: undefined result variable {action.result_variable}.")
            if types[action.result_variable] != expected:
                raise ValueError(
                    f"Action {index + 1}: result variable must be {expected}.")
    return definitions


def parse_value(text, kind):
    """Small editor value parser; blanks mean unset (except text: use quotes)."""
    if not isinstance(text, str):
        raise ValueError("Variable input must be text.")
    if not text.strip():
        return None
    if kind == "text":
        return text
    if kind == "boolean":
        if text.lower() in ("true", "false"):
            return text.lower() == "true"
        raise ValueError("Boolean values must be true or false.")
    if kind == "coordinates":
        parts = text.split(",")
        if len(parts) != 2:
            raise ValueError("Coordinates must be two integers: x,y.")
        try:
            return _type_value([int(v.strip()) for v in parts], kind)
        except (ValueError, TypeError):
            raise ValueError("Coordinates must be two integers: x,y.") from None
    if kind == "number":
        try:
            value = float(text)
        except ValueError:
            raise ValueError("Number must be a finite numeric value.") from None
        return _type_value(value, kind)
    raise ValueError("Unknown variable type.")


def format_value(value, kind):
    if value is None:
        return ""
    if kind == "coordinates":
        return f"{value[0]},{value[1]}"
    if kind == "boolean":
        return "true" if value else "false"
    return str(value)


class VariableMissing(ValueError):
    """A referenced variable has not received a default or result yet."""


class VariableContext:
    def __init__(self, definitions, overrides=None):
        self.definitions = validate_variables(definitions)
        self.types = {item["name"]: item["type"] for item in self.definitions}
        self.overrides = {}
        for name, value in (overrides or {}).items():
            if name not in self.types:
                raise ValueError(f"Unknown run override variable {name}.")
            self.overrides[name] = _type_value(value, self.types[name])
        self.reset()

    def reset(self):
        self.values = {
            item["name"]: item["default"] for item in self.definitions
        }
        self.values.update(self.overrides)

    def get(self, name):
        value = self.values[name]
        if value is None:
            raise VariableMissing(
                f"Variable {name} is unset. Assign its default, run override, "
                "or an earlier action result before use.")
        return value

    def set_result(self, name, value):
        if name not in self.types:
            raise ValueError("Output variable is not defined.")
        converted = _type_value(value, self.types[name])
        if converted is None:
            raise ValueError("Action output cannot be unset.")
        self.values[name] = converted

    def resolve(self, action):
        if not action.bindings:
            return action
        values = {}
        for field, name in action.bindings.items():
            value = self.get(name)
            if field in ("point", "to_point"):
                x, y = ("x", "y") if field == "point" else ("to_x", "to_y")
                values.update({x: value[0], y: value[1]})
                continue
            if field in ("scroll_amount", "image_offset_x", "image_offset_y",
                         "pixel_x", "pixel_y"):
                if type(value) is float and value.is_integer():
                    value = int(value)
                if type(value) is not int:
                    raise ValueError(f"{field} requires a whole-number variable value.")
            values[field] = value
        # Revalidate the *resolved* action. For example, a numeric variable
        # must not bypass Wait >= 0 or a Click Image confidence constraint.
        from dataclasses import asdict
        from macro_model import validate_action
        return validate_action(asdict(replace(action, **values, bindings={})))


def unset_warnings(actions, definitions, start_index=0, overrides=None):
    """Conservative warnings: an unset variable has no earlier producer."""
    values = VariableContext(definitions, overrides).values
    producer = set()
    warnings = []
    for i in range(start_index, len(actions)):
        action = actions[i]
        if not action.enabled:
            continue
        for name in action.bindings.values():
            if values.get(name) is None and name not in producer:
                warnings.append((i, f"Variable {name} has no default or "
                                    "earlier output in this run."))
        if action.result_variable:
            producer.add(action.result_variable)
    return warnings
