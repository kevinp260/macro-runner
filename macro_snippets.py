"""Local, copy-only reusable workflow snippets (independent of the Qt editor)."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path, PureWindowsPath
import re
import uuid

from macro_model import parse_sequence
from macro_recovery import atomic_json_write
from macro_variables import validate_references, validate_variables

SCHEMA = 1
FORMAT = "macro-runner-snippet"
MAX_BYTES = 2_000_000
MAX_ACTIONS = 2000
_ID = re.compile(r"^[0-9a-f]{32}$")
_IMAGE_ACTIONS = frozenset(("click_image", "wait_until", "if_start", "until_start"))


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise ValueError("Snippet name must contain 1–80 characters.")
    return value.strip()


def _actions(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ACTIONS:
        raise ValueError("Snippet must contain 1–2000 actions.")
    try:
        return parse_sequence(value)
    except (RecursionError, TypeError) as exc:
        raise ValueError("Snippet has invalid or excessively nested actions.") from exc


def _references(actions):
    names = set()
    for action in actions:
        names.update(action.bindings.values())
        if action.result_variable:
            names.add(action.result_variable)
    return names


def _portable_image_paths(actions, base_dir):
    """Anchor relative images to their original folder, not the snippet library."""
    if base_dir is None:
        return actions
    for action in actions:
        if (action.kind in _IMAGE_ACTIONS and
                action.condition_source == "image" and
                "image_path" not in action.bindings and action.image_path):
            path = action.image_path
            if not Path(path).is_absolute() and not PureWindowsPath(path).is_absolute():
                action.image_path = str((Path(base_dir) / path).resolve())
    return actions


def normalize_snippet(value):
    """Refuse malformed or unsupported snippet documents before editing a workflow."""
    if not isinstance(value, dict) or set(value) != {
            "format", "version", "mode", "name", "actions", "variables"}:
        raise ValueError("Not a MacroRunner snippet file.")
    if (value["format"] != FORMAT or value["version"] != SCHEMA or
            value["mode"] != "copy"):
        raise ValueError("Unsupported snippet version or link mode.")
    actions = _actions(value["actions"])
    definitions = validate_variables(value["variables"])
    used = _references(actions)
    if {item["name"] for item in definitions} != used:
        raise ValueError("Snippet variable declarations do not match its dependencies.")
    validate_references(actions, definitions)
    return {
        "format": FORMAT, "version": SCHEMA, "mode": "copy",
        "name": _name(value["name"]),
        "actions": [asdict(action) for action in actions],
        "variables": definitions,
    }


def make_snippet(name, actions, definitions, base_dir=None):
    """Snapshot a selection. Do not silently carry text variable defaults/secrets."""
    copied = _actions([asdict(action) for action in actions])
    copied = _portable_image_paths(copied, base_dir)
    declared = validate_references(copied, definitions)
    used = _references(copied)
    dependencies = []
    for item in declared:
        if item["name"] in used:
            entry = deepcopy(item)
            if entry["type"] == "text":
                entry["default"] = None  # Explicitly reconfigure sensitive text defaults.
            dependencies.append(entry)
    return normalize_snippet({
        "format": FORMAT, "version": SCHEMA, "mode": "copy",
        "name": name, "actions": [asdict(a) for a in copied],
        "variables": dependencies,
    })


def _check_images(actions, definitions):
    values = {item["name"]: item["default"] for item in definitions}
    for action in actions:
        if action.kind not in _IMAGE_ACTIONS or action.condition_source != "image":
            continue
        image_path = (values.get(action.bindings["image_path"])
                      if "image_path" in action.bindings else action.image_path)
        if image_path is None:
            continue  # A runtime producer or run override may supply the image path.
        if not isinstance(image_path, str) or not image_path.strip():
            raise ValueError("Snippet image reference is empty.")
        if PureWindowsPath(image_path).is_absolute() and not Path(image_path).is_absolute():
            raise ValueError(
                f"Image path is from another operating system: {image_path}. "
                "Choose a local reference image before inserting.")
        path = Path(image_path).expanduser()
        if not path.is_file():
            raise ValueError(
                f"Snippet image is missing: {image_path}. "
                "Restore the image or update the snippet before inserting.")
        # The runtime uses Pillow; checking readability here avoids inserting
        # an unusable file which would fail when the macro executes.
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(path) as image:
                image.verify()
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            raise ValueError(f"Snippet image is unreadable: {image_path}") from exc


def prepare_insertion(snippet, destination_variables):
    """Validate and return copied actions plus merged declarations; no mutation."""
    data = normalize_snippet(snippet)
    existing = validate_variables(destination_variables)
    known = {item["name"]: item for item in existing}
    merged = deepcopy(existing)
    for dependency in data["variables"]:
        prior = known.get(dependency["name"])
        if prior is not None:
            if prior["type"] != dependency["type"]:
                raise ValueError(
                    f"Variable {dependency['name']} has type {prior['type']} "
                    f"in this workflow, but the snippet expects {dependency['type']}.")
            # Existing workflow values win; never replace them on insertion.
        else:
            merged.append(deepcopy(dependency))
            known[dependency["name"]] = dependency
    merged = validate_variables(merged)
    actions = _actions(data["actions"])
    validate_references(actions, merged)
    _check_images(actions, merged)
    return actions, merged


class SnippetStore:
    """Private per-user JSON files, addressed only by generated UUIDs."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, snippet_id):
        if not isinstance(snippet_id, str) or not _ID.fullmatch(snippet_id):
            raise ValueError("Invalid snippet identifier.")
        return self.directory / (snippet_id + ".json")

    @staticmethod
    def _read_path(path):
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError("Snippet file is missing, a link, or exceeds 2 MB.")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            return normalize_snippet(document)
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("Snippet file is unreadable or malformed.") from exc

    def read(self, snippet_id):
        return self._read_path(self._path(snippet_id))

    def list(self):
        if not self.directory.exists():
            return []
        items = []
        for path in self.directory.glob("*.json"):
            if not _ID.fullmatch(path.stem):
                continue
            try:
                data = self.read(path.stem)
            except (OSError, ValueError, TypeError):
                continue  # One corrupt snippet must not make the library unusable.
            items.append({
                "id": path.stem, "name": data["name"],
                "actions": len(data["actions"]),
                "variables": len(data["variables"]),
            })
        return sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))

    def _write(self, snippet_id, document):
        normalized = normalize_snippet(document)
        if len(json.dumps(normalized, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
            raise ValueError("Snippet exceeds 2 MB.")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_json_write(self._path(snippet_id), normalized, max_bytes=MAX_BYTES)

    def save(self, document):
        snippet_id = uuid.uuid4().hex
        self._write(snippet_id, document)
        return snippet_id

    def rename(self, snippet_id, name):
        data = self.read(snippet_id)
        data["name"] = _name(name)
        self._write(snippet_id, data)

    def replace(self, snippet_id, document):
        self.read(snippet_id)  # Never create missing/deleted entries by accident.
        self._write(snippet_id, document)

    def delete(self, snippet_id):
        self.read(snippet_id)
        self._path(snippet_id).unlink()

    def import_file(self, path):
        data = self._read_path(path)
        actions = _actions(data["actions"])
        _portable_image_paths(actions, Path(path).parent)
        data["actions"] = [asdict(action) for action in actions]
        return self.save(data)

    def export_file(self, snippet_id, path):
        data = self.read(snippet_id)
        atomic_json_write(path, data, max_bytes=MAX_BYTES)
