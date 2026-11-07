"""Release/versioning contract tests shared by Ubuntu and Windows CI."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from macro_qt import MacroWindow
from macro_version import app_version, main, project_version

ROOT = Path(__file__).resolve().parents[1]
app = QApplication.instance() or QApplication([])


class VersioningTests(unittest.TestCase):
    def test_source_checkout_uses_pyproject_version(self):
        expected = project_version(ROOT / "pyproject.toml")
        self.assertEqual(app_version(), expected)
        self.assertRegex(expected, r"^\d+\.\d+\.\d+$")

    def test_read_only_project_table_and_reject_invalid_version(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "pyproject.toml"
            target.write_text('[build-system]\nversion = "9.9.9"\n'
                              '[project]\nname = "some-app"\nversion = "3.2.1"\n'
                              '[tool.x]\nversion = "4.0.0"\n', encoding="utf-8")
            self.assertEqual(project_version(target), "3.2.1")
            target.write_text('[project]\nversion = "bad"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                project_version(target)

    def test_tag_must_match_project_version(self):
        expected = project_version(ROOT / "pyproject.toml")
        self.assertEqual(main(["--check-tag", "v" + expected]), 0)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as cm:
            main(["--check-tag", "v999.0.0"])
        self.assertEqual(cm.exception.code, 2)

    def test_about_dialog_reports_application_version(self):
        window = MacroWindow()
        try:
            titles = [action.text() for action in window.menuBar().actions()]
            self.assertIn("Help", titles)
            with patch("macro_qt.QMessageBox.about") as about:
                window.show_about()
            self.assertEqual(about.call_count, 1)
            self.assertIn("MacroRunner v" + app_version(), about.call_args.args[2])
            self.assertIn("github.com/kevinp260/macro-runner",
                          about.call_args.args[2])
        finally:
            window.close()

    def test_installer_uses_authoritative_version(self):
        iss = (ROOT / "installer.iss").read_text()
        spec = (ROOT / "MacroRunner.spec").read_text()
        ubuntu = (ROOT / "packaging/build-deb.sh").read_text()
        workflow = (ROOT / ".github/workflows/installers.yml").read_text()
        self.assertIn("#ifndef MyAppVersion", iss)
        self.assertNotIn('#define MyAppVersion  "2.0.0"', iss)
        self.assertIn("copy_metadata('macro-runner-desktop')", spec)
        self.assertIn("python3 -m macro_version", ubuntu)
        self.assertIn('/DMyAppVersion=$version', workflow)
        self.assertIn('refs/tags/v', workflow)
        self.assertIn('needs: [version-check, ubuntu-deb, windows-installer]', workflow)
        self.assertIn('gh release create', workflow)
        self.assertIn('fail-fast: false',
                      (ROOT / ".github/workflows/python-checks.yml").read_text())


if __name__ == "__main__":
    unittest.main()
