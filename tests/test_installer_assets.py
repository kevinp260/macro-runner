"""Packaging contract checks, runnable on Ubuntu and Windows."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerAssetsTests(unittest.TestCase):
    def test_qt_and_screenshot_packages_declared(self):
        text = (ROOT / "packaging/ubuntu-dependencies.txt").read_text()
        packages = set(re.findall(r"(?m)^[a-z][a-z0-9+.-]+$", text))
        self.assertTrue({"libxcb-cursor0", "libegl1", "libopengl0",
                         "libxkbcommon0", "scrot"} <= packages)

    def test_install_script_prompts_before_elevation(self):
        script = (ROOT / "install-ubuntu.sh").read_text()
        self.assertIn("read -r -p", script)
        self.assertIn("sudo apt-get install", script)
        self.assertIn("pipx install --force .", script)
        self.assertIn("id -u", script)

    def test_both_installer_jobs_exist(self):
        workflow = (ROOT / ".github/workflows/installers.yml").read_text()
        self.assertIn("ubuntu-24.04", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn("packaging/build-deb.sh", workflow)
        self.assertIn("installer.iss", workflow)

    def test_windows_upgrade_identity_is_stable(self):
        text = (ROOT / "installer.iss").read_text()
        self.assertIn("8F6B8A3D-5D6E-4E62-9C0D-0D0FBF9A8F22", text)
        self.assertIn("MacroRunner.exe", text)
