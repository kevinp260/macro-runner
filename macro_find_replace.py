"""Search flat workflow actions and plan validated atomic bulk replacements.

The flat action order includes nested group markers; searches can find them,
but structural markers and variable-bound values are never bulk-edited.
"""
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PureWindowsPath
import math
import re

from macro_flow import CONTROL, validate_flow
from macro_model import validate_action
from macro_variables import validate_references


SEARCH_FIELDS = (
    ("all", "All searchable fields"),
    ("kind", "Action type"),
    ("name", "Name"),
    ("enabled", "Enabled / disabled"),
    ("keys", "Keyboard key / text"),
    ("coordinates", "Coordinates"),
    ("image", "Image filename"),
)

# A small, explicit allowlist; no action-kind, group, enabled or binding edits.
REPLACE_FIELDS = {
    "name": ("Name", "text", None),
    "keys": ("Keyboard key / text", "text", {"key", "key_down", "key_up"}),
    "x": ("X coordinate", "integer", {"click", "move", "drag"}),
    "y": ("Y coordinate", "integer", {"click", "move", "drag"}),
    "to_x": ("Destination X", "integer", {"drag"}),
    "to_y": ("Destination Y", "integer", {"drag"}),
    "image_path": ("Reference image path", "text", {"click_image", "wait_until"}),
    "seconds": ("Wait seconds", "number", {"wait"}),
    "scroll_amount": ("Scroll steps", "integer", {"scroll"}),
    "text_target": ("OCR phrase", "text", {"find_text", "wait_text"}),
    "timeout": ("Timeout seconds", "number",
                {"click_image", "wait_until", "file_wait", "wait_window", "wait_text"}),
}

COORDINATES = ("x", "y", "to_x", "to_y", "region_x", "region_y",
               "pixel_x", "pixel_y")
INTEGER = re.compile(r"[+-]?\d+\Z")


@dataclass(frozen=True)
class SearchMatch:
    index: int
    field: str


@dataclass(frozen=True)
class Replacement:
    index: int
    old: object
    new: object


@dataclass(frozen=True)
class ReplacementPlan:
    actions: tuple
    changes: tuple
    skipped: int


def _terms(action):
    coordinates = [f"{key}={getattr(action, key)}"
                   for key in COORDINATES if getattr(action, key) is not None]
    return {
        "kind": (action.kind.replace("_", " "), action.kind),
        "name": (action.name,),
        "enabled": (("enabled", "true", "yes", "1") if action.enabled
                    else ("disabled", "false", "no", "0")),
        "keys": (action.keys,) if action.kind in ("key", "key_down", "key_up") else (),
        "coordinates": tuple(coordinates),
        "image": (PureWindowsPath(action.image_path).name,)
                 if action.image_path else (),
    }


def search_actions(actions, query, field="all"):
    """Return matching flat indices, including children of collapsed groups."""
    if field not in dict(SEARCH_FIELDS):
        raise ValueError("Unsupported workflow search field.")
    if not isinstance(query, str):
        raise ValueError("Search must be text.")
    needle = query.strip().casefold()
    if not needle:
        return []
    found = []
    for index, action in enumerate(actions):
        terms = _terms(action)
        fields = terms.keys() if field == "all" else (field,)
        for selected in fields:
            if selected == "enabled":
                ok = needle in terms[selected]  # Exact boolean, not substring.
            else:
                ok = any(needle in value.casefold() for value in terms[selected])
            if ok:
                found.append(SearchMatch(index, selected))
                break
    return found


def _parse_value(text, kind):
    if kind == "text":
        return text
    if kind == "integer":
        if not INTEGER.fullmatch(text.strip()):
            raise ValueError("Enter an integer without decimals.")
        return int(text.strip())
    try:
        value = float(text.strip())
    except ValueError as exc:
        raise ValueError("Enter a finite number.") from exc
    if not math.isfinite(value):
        raise ValueError("Enter a finite number.")
    return value


def _bound(action, field):
    if field in action.bindings:
        return True
    return ((field in ("x", "y") and "point" in action.bindings) or
            (field in ("to_x", "to_y") and "to_point" in action.bindings))


def _compatible(action, field):
    if action.kind in CONTROL:
        return False
    allowed = REPLACE_FIELDS[field][2]
    if allowed is not None and action.kind not in allowed:
        return False
    if field == "image_path" and action.condition_source != "image":
        return False
    return not _bound(action, field)


def _check_image_path(value, base_dir):
    from PIL import Image
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path
    if not path.is_file():
        raise ValueError("Reference image does not exist: " + str(path))
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, ValueError) as exc:
        raise ValueError("Reference image is not readable: " + str(path)) from exc


def plan_replacements(actions, indices, field, text, *, mode="set",
                      find_text="", variables=None, base_dir=None):
    """Validate every candidate before exposing a plan for one Undoable edit.

    Invalid changes abort the entire operation. Nonmatching kinds and bound
    fields are skipped, never overwritten or silently substituted at runtime.
    """
    if field not in REPLACE_FIELDS:
        raise ValueError("Only listed text and numeric action fields may be replaced.")
    if mode not in ("set", "replace"):
        raise ValueError("Choose Set value or Replace substring.")
    if not isinstance(text, str) or not isinstance(find_text, str):
        raise ValueError("Replacement values must be text inputs.")
    kind = REPLACE_FIELDS[field][1]
    if mode == "replace" and kind != "text":
        raise ValueError("Substring replace is only available for text fields.")
    if mode == "replace" and not find_text:
        raise ValueError("Enter the nonempty substring to replace.")
    if not indices:
        raise ValueError("Search for actions before replacing.")
    if any(type(i) is not int or i < 0 or i >= len(actions) for i in indices):
        raise ValueError("Search result indices are no longer valid.")

    value = _parse_value(text, kind) if mode == "set" else None
    proposed = list(actions)
    changes = []
    skipped = 0
    for index in sorted(set(indices)):
        action = actions[index]
        if not _compatible(action, field):
            skipped += 1
            continue
        old = getattr(action, field)
        new = old.replace(find_text, text) if mode == "replace" else value
        if old == new:
            continue
        try:
            edited = validate_action(asdict(replace(action, **{field: new})))
            if field == "image_path":
                _check_image_path(new, base_dir)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Action {index + 1}: {exc}") from exc
        proposed[index] = edited
        changes.append(Replacement(index, old, new))
    if not changes:
        raise ValueError("No eligible, unbound action values would change.")
    validate_flow(proposed)
    validate_references(proposed, list(variables or []))
    return ReplacementPlan(tuple(proposed), tuple(changes), skipped)
