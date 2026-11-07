"""Small, shell-free local file actions with explicit paths and no delete action.

Paths are OS-native, absolute and never inferred from the current directory.
Copy/move refuse existing destinations by default; opt-in replacement uses a
temporary file in the destination directory before committing with os.replace.
"""
import os
from pathlib import Path
import shutil
import stat
import tempfile


FILE_KINDS = frozenset(("file_check", "file_wait", "file_copy",
                        "file_move", "folder_create"))
MUTATING = frozenset(("file_copy", "file_move", "folder_create"))
CHUNK = 1024 * 1024


class FileActionError(ValueError):
    """Invalid or unsafe local file operation."""


def local_path(value, description, *, required=True):
    """Validate one explicit OS-native absolute path without filesystem I/O."""
    if not isinstance(value, str):
        raise FileActionError(f"{description} must be text.")
    if not value and not required:
        return None  # Editable placeholder. Preflight blocks execution.
    if not value or value != value.strip() or any(
            c in value for c in ("\x00", "\r", "\n")):
        raise FileActionError(f"Enter a valid {description.lower()} path.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise FileActionError(
            f"{description} must be an absolute local path; select it using Browse.")
    if ".." in Path(value).parts:
        raise FileActionError(
            f"{description} cannot contain parent-directory traversal (..).")
    if path == path.parent:
        raise FileActionError(f"{description} cannot be a filesystem root.")
    return path


def validate_file_action(action, *, require_paths=False):
    """Validate model configuration, including unused existing default fields."""
    if action.kind not in FILE_KINDS:
        raise FileActionError("Unknown file action.")
    src = local_path(action.file_path, "File/folder",
                     required=require_paths)
    dest = None
    if action.kind in ("file_copy", "file_move"):
        dest = local_path(action.file_destination, "Destination",
                          required=require_paths)
    if not isinstance(action.file_overwrite, bool):
        raise FileActionError("Overwrite must be true or false.")
    if action.kind == "file_wait":
        if isinstance(action.timeout, bool) or not isinstance(action.timeout, (int, float)):
            raise FileActionError("File wait timeout must be a number.")
        if not 0 <= action.timeout <= 86400:
            raise FileActionError("File wait timeout must be between 0 and 86400 seconds.")
        if isinstance(action.poll_interval, bool) or not isinstance(
                action.poll_interval, (int, float)):
            raise FileActionError("File poll interval must be a number.")
        if not 0.1 <= action.poll_interval <= 60:
            raise FileActionError("File poll interval must be between 0.1 and 60 seconds.")
    return src, dest


def _regular_source(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"Source file does not exist: {path}") from None
    if not stat.S_ISREG(info.st_mode):
        raise FileActionError("Source must be a regular file, not a folder or symlink.")
    return path


def _destination_check(src, dest, overwrite):
    if not dest.parent.is_dir():
        raise FileNotFoundError(
            f"Destination directory does not exist: {dest.parent}. "
            "Add a Create folder action first.")
    if dest.is_symlink():
        raise FileActionError("Destination is a symlink and cannot be replaced.")
    if dest.exists():
        if not dest.is_file():
            raise FileActionError("Destination must be a file, not a folder.")
        if os.path.samefile(src, dest):
            raise FileActionError("Source and destination refer to the same file.")
        if not overwrite:
            raise FileExistsError(
                f"Destination already exists: {dest}. Enable Overwrite to replace it.")
    elif src.resolve() == dest.resolve():
        raise FileActionError("Source and destination refer to the same file.")


def _copy_chunks(src, writer, gate):
    with src.open("rb") as reader:
        while True:
            gate.wait(0)
            block = reader.read(CHUNK)
            if not block:
                break
            writer.write(block)


def _copy_no_overwrite(src, dest, gate):
    # Exclusive create ensures a concurrent file does not get overwritten.
    created = False
    try:
        with dest.open("xb") as writer:
            created = True
            _copy_chunks(src, writer, gate)
        shutil.copystat(src, dest)
        gate.wait(0)
    except BaseException:
        # Only remove a file we created as part of this failed operation.
        if created:
            try:
                dest.unlink()
            except OSError:
                pass
        raise


def _copy_replace(src, dest, gate):
    # Never touch the previous destination before the entire new copy is
    # complete. A failed/Stopped write leaves existing content intact.
    name = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", dir=str(dest.parent),
                prefix=".macrorunner-copy-", delete=False) as writer:
            name = Path(writer.name)
            _copy_chunks(src, writer, gate)
        shutil.copystat(src, name)
        gate.wait(0)
        # Refuse a symlink installed after the earlier validation.
        if dest.is_symlink():
            raise FileActionError("Destination changed to a symlink during copy.")
        os.replace(name, dest)
        name = None
    finally:
        if name is not None:
            try:
                name.unlink()
            except OSError:
                pass


def run_file_action(action, gate):
    """Perform one configured action; never invoke a shell or delete trees."""
    src, dest = validate_file_action(action, require_paths=True)
    gate.wait(0)
    if action.kind in ("file_check", "file_wait"):
        if action.kind == "file_check":
            if not src.is_file():
                raise FileNotFoundError(f"File does not exist: {src}")
            return
        remaining = action.timeout
        while True:
            gate.wait(0)
            if src.is_file():
                return
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for file: {src}")
            interval = min(remaining, action.poll_interval)
            gate.wait(interval)
            remaining -= interval

    if action.kind == "folder_create":
        # Existing real directories are allowed (idempotent). A symlink in
        # the final path is never treated as a folder to create.
        if src.is_symlink():
            raise FileActionError("Create folder refuses a symbolic-link target.")
        src.mkdir(parents=True, exist_ok=True)
        return

    _regular_source(src)
    _destination_check(src, dest, action.file_overwrite)
    gate.wait(0)
    if action.file_overwrite:
        _copy_replace(src, dest, gate)
    else:
        _copy_no_overwrite(src, dest, gate)
    if action.kind == "file_move":
        # The new destination has been committed. Removing only this source
        # file is the explicitly requested Move action, not a Delete action.
        # Do not cancel between destination commit and source unlink.
        src.unlink()
