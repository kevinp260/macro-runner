"""Runtime/build version derived from the project's sole version source.

In a source checkout read pyproject.toml. pipx installs and PyInstaller bundles
use the installed distribution metadata (collected by MacroRunner.spec).
This module also serves as the shared CLI for installer builds and release tags.
"""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import argparse
import re
import sys

DISTRIBUTION = "macro-runner-desktop"
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")


def project_version(path=None):
    """Read the [project] version without requiring tomllib on Python 3.9."""
    path = Path(path) if path is not None else Path(__file__).with_name("pyproject.toml")
    content = path.read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", content)
    if not project:
        raise ValueError(f"Missing [project] in {path}")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', project.group(1))
    if not match or not VERSION_PATTERN.fullmatch(match.group(1)):
        raise ValueError("Project version must use MAJOR.MINOR.PATCH in pyproject.toml.")
    return match.group(1)


def app_version():
    """Return the version for source, pipx, and frozen Windows/Linux builds."""
    source = Path(__file__).with_name("pyproject.toml")
    if not getattr(sys, "frozen", False) and source.is_file():
        return project_version(source)
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print or validate MacroRunner version.")
    parser.add_argument("--check-tag", help="Require the tag to match vMAJOR.MINOR.PATCH")
    args = parser.parse_args(argv)
    current = project_version()
    if args.check_tag and args.check_tag != f"v{current}":
        parser.error(f"release tag {args.check_tag!r} does not match v{current}")
    print(current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
