"""Portable ZIP workflow packages; no extraction outside app-managed assets.

The package contains only a version-2 workflow, a manifest, and referenced
image files. Import validates every entry before writing anything locally.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import stat
import tempfile
import uuid
import zipfile

from PIL import Image, UnidentifiedImageError

from macro_model import parse_document, serialize_document

FORMAT = "macro-runner-package"
VERSION = 1
EXTENSIONS = {"PNG": "png", "JPEG": "jpg", "BMP": "bmp",
              "GIF": "gif", "WEBP": "webp"}
IMAGE_ACTIONS = frozenset(("click_image", "wait_until", "if_start", "until_start"))
ASSET_NAME = re.compile(r"assets/([0-9a-f]{64})\.(png|jpg|bmp|gif|webp)")
MAX_IMAGES = 128
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class PackagePlan:
    workflow: dict
    # (archive name, source path, byte size, sha256)
    assets: tuple
    warnings: tuple


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _valid_workflow(document):
    actions, settings = parse_document(document)
    if settings is None:
        raise ValueError("A portable package requires a version-2 workflow.")
    return serialize_document(
        actions, settings["repeat_count"], settings["start_delay"],
        settings.get("window_target"), settings.get("variables", []))


def _image_sources(workflow):
    """Yield each active image reference, including bound variable defaults."""
    variables = {entry["name"]: entry for entry in
                 workflow["settings"].get("variables", [])}
    for action in workflow["actions"]:
        if action["kind"] not in IMAGE_ACTIONS or action["condition_source"] != "image":
            continue
        binding = action["bindings"].get("image_path")
        if binding:
            # The stored literal is not used when a binding is active.
            action["image_path"] = ""
            yield variables[binding], "default"
        else:
            yield action, "image_path"


def _image_file(value, base_dir):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("An image reference is empty.")
    path = Path(value).expanduser()
    if PureWindowsPath(value).drive and os.name != "nt":
        raise ValueError(f"Image path is from a different OS: {value}")
    if not path.is_absolute():
        if base_dir is None:
            raise ValueError("Relative image paths need the workflow directory.")
        path = Path(base_dir) / path
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Reference image is missing or a symlink: {value}")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"Reference image exceeds 16 MiB: {value}")
    return path


def _identify_image(path):
    try:
        with Image.open(path) as image:
            image_format = image.format
            if image_format not in EXTENSIONS:
                raise ValueError(f"Unsupported reference image format: {path}")
            if image.width * image.height > 50_000_000:
                raise ValueError(f"Reference image exceeds 50 million pixels: {path}")
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Reference image is unreadable: {path}") from exc
    return EXTENSIONS[image_format]


def _digest_file(path):
    total = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ValueError(f"Reference image exceeds 16 MiB: {path}")
            digest.update(chunk)
    return total, digest.hexdigest()


def plan_package(document, source_dir=None):
    """Validate and prepare an export without changing the source workflow."""
    workflow = _valid_workflow(document)
    assets = {}
    warnings = []
    for owner, field in _image_sources(workflow):
        value = owner[field]
        if value is None:
            if "Image-path variables without defaults require a local run override." not in warnings:
                warnings.append("Image-path variables without defaults require a local run override.")
            continue
        path = _image_file(value, source_dir)
        extension = _identify_image(path)
        size, digest = _digest_file(path)
        name = f"assets/{digest}.{extension}"
        if name not in assets:
            assets[name] = (name, path, size, digest)
        owner[field] = name

    if len(assets) > MAX_IMAGES:
        raise ValueError("Package contains too many distinct images (maximum 128).")
    if any(item["kind"] in ("file_check", "file_wait", "file_copy",
                            "file_move", "folder_create", "launch", "wait_window")
           for item in workflow["actions"]) or "window_target" in workflow["settings"]:
        warnings.append("Other local paths and window targets are not rebased; review them on the new machine.")
    if (any(item["kind"] == "clipboard_set" or
            (item["kind"] == "key" and item["key_mode"] == "type")
            for item in workflow["actions"]) or
            any(item["type"] == "text" and item["default"] is not None
                for item in workflow["settings"].get("variables", []))):
        warnings.append("Typed text, clipboard contents and variable defaults remain plain text in the package.")
    if assets:
        warnings.append("Images may include sensitive screen captures. Review the source files before sharing.")
    if len(_json_bytes(workflow)) > MAX_DOCUMENT_BYTES:
        raise ValueError("Workflow document exceeds the 8 MiB package limit.")
    if sum(item[2] for item in assets.values()) + len(_json_bytes(workflow)) > MAX_TOTAL_BYTES:
        raise ValueError("Package contents exceed the 64 MiB limit.")
    return PackagePlan(workflow, tuple(assets.values()), tuple(warnings))


def export_package(destination, document, source_dir=None):
    """Write one validated package atomically; never leave partial ZIPs."""
    plan = plan_package(document, source_dir)
    write_package(destination, plan)
    return plan


def write_package(destination, plan):
    destination = Path(destination)
    manifest = {
        "format": FORMAT, "version": VERSION,
        "assets": [{"name": name, "size": size, "sha256": digest}
                   for name, _, size, digest in plan.assets],
    }
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix=".macro-package-", suffix=".tmp",
                                   dir=destination.parent)
        os.close(fd)
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=False) as archive:
            archive.writestr("manifest.json", _json_bytes(manifest))
            archive.writestr("workflow.json", _json_bytes(plan.workflow))
            for name, source, size, digest in plan.assets:
                # Re-check sources during streaming to detect races/changed files.
                written = 0
                checksum = hashlib.sha256()
                with source.open("rb") as reader, archive.open(name, "w") as writer:
                    while chunk := reader.read(CHUNK):
                        written += len(chunk)
                        if written > MAX_IMAGE_BYTES:
                            raise ValueError(f"Reference image grew too large: {source}")
                        checksum.update(chunk)
                        writer.write(chunk)
                if written != size or checksum.hexdigest() != digest:
                    raise ValueError(f"Reference image changed during export: {source}")
        if Path(temp).stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Portable package exceeds the 64 MiB archive limit.")
        os.replace(temp, destination)
        temp = None
    finally:
        if temp is not None:
            Path(temp).unlink(missing_ok=True)


def _read_limited(archive, name, maximum):
    with archive.open(name) as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"Package entry exceeds its size limit: {name}")
    return data


def _validated_archive(archive):
    infos = archive.infolist()
    if len(infos) > MAX_IMAGES + 2 or len(infos) < 2:
        raise ValueError("Invalid package entry count.")
    entries = {}
    total = 0
    for info in infos:
        name = info.filename
        mode = (info.external_attr >> 16) & 0o170000
        if (name in entries or name not in ("manifest.json", "workflow.json") and
                ASSET_NAME.fullmatch(name) is None or info.is_dir() or
                mode not in (0, stat.S_IFREG) or info.flag_bits & 1):
            raise ValueError(f"Unsafe or unsupported archive entry: {name}")
        if info.file_size < 0 or info.file_size > (
                MAX_IMAGE_BYTES if name.startswith("assets/") else MAX_DOCUMENT_BYTES):
            raise ValueError(f"Package entry is too large: {name}")
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Uncompressed package exceeds 64 MiB.")
        entries[name] = info

    if "manifest.json" not in entries or "workflow.json" not in entries:
        raise ValueError("Package must contain manifest.json and workflow.json.")
    if entries["manifest.json"].file_size > 128_000:
        raise ValueError("Package manifest is too large.")
    try:
        manifest = json.loads(_read_limited(archive, "manifest.json", 128_000))
        workflow = json.loads(_read_limited(archive, "workflow.json", MAX_DOCUMENT_BYTES))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("Package metadata or workflow JSON is invalid.") from exc

    if (not isinstance(manifest, dict) or set(manifest) !=
            {"format", "version", "assets"} or
            manifest["format"] != FORMAT or manifest["version"] != VERSION or
            not isinstance(manifest["assets"], list)):
        raise ValueError("Unsupported portable package format.")
    expected = {}
    for item in manifest["assets"]:
        if (not isinstance(item, dict) or set(item) !=
                {"name", "size", "sha256"} or
                not isinstance(item["name"], str) or
                ASSET_NAME.fullmatch(item["name"]) is None or
                not isinstance(item["size"], int) or isinstance(item["size"], bool) or
                not isinstance(item["sha256"], str) or
                item["name"].split("/")[1].split(".")[0] != item["sha256"] or
                item["name"] in expected):
            raise ValueError("Invalid or duplicate package asset declaration.")
        expected[item["name"]] = item
    if set(entries) != set(expected) | {"manifest.json", "workflow.json"}:
        raise ValueError("Archive entries do not match its manifest.")
    for name, item in expected.items():
        if item["size"] != entries[name].file_size:
            raise ValueError(f"Package asset size mismatch: {name}")
    normalized = _valid_workflow(workflow)
    # All image references must resolve only to files declared in this package.
    for owner, field in _image_sources(normalized):
        value = owner[field]
        if value is not None and value not in expected:
            raise ValueError(f"Workflow image reference is not packaged: {value}")
    return normalized, expected


def inspect_package(source):
    """Read and validate metadata only; no files created or overwritten."""
    source = Path(source)
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Portable package exceeds 64 MiB.")
    try:
        with zipfile.ZipFile(source) as archive:
            workflow, expected = _validated_archive(archive)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
        raise ValueError("Portable package is corrupt or unsupported.") from exc
    return {"image_count": len(expected),
            "image_bytes": sum(item["size"] for item in expected.values()),
            "has_text": any(a["kind"] == "clipboard_set" or
                            a["kind"] == "key" and a["key_mode"] == "type"
                            for a in workflow["actions"]),
            "has_variables": bool(workflow["settings"].get("variables"))}


def import_package(source, assets_root):
    """Validate, stage, verify checksums, then atomically install referenced assets."""
    source = Path(source)
    # Validate the whole archive before creating any directories.
    inspect_package(source)
    root = Path(assets_root).expanduser()
    if root.is_symlink():
        raise ValueError("Managed assets directory cannot be a symlink.")
    with zipfile.ZipFile(source) as archive:
        workflow, expected = _validated_archive(archive)
        if not expected:
            return workflow
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        destination = root / uuid.uuid4().hex
        if destination.exists():
            raise ValueError("Managed assets destination already exists.")
        stage = Path(tempfile.mkdtemp(prefix=".import-", dir=root))
        try:
            replacements = {}
            for name, item in expected.items():
                output = stage / Path(name).name
                checksum = hashlib.sha256()
                count = 0
                with archive.open(name) as reader, output.open("xb") as writer:
                    while chunk := reader.read(CHUNK):
                        count += len(chunk)
                        if count > MAX_IMAGE_BYTES:
                            raise ValueError("Package image expanded beyond limit.")
                        checksum.update(chunk)
                        writer.write(chunk)
                if count != item["size"] or checksum.hexdigest() != item["sha256"]:
                    raise ValueError(f"Package asset checksum mismatch: {name}")
                _identify_image(output)
                replacements[name] = str(destination / output.name)
            for owner, field in _image_sources(workflow):
                if owner[field] is not None:
                    owner[field] = replacements[owner[field]]
            _valid_workflow(workflow)
            os.rename(stage, destination)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    return workflow
