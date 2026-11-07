"""Explicitly discard test-only editor changes when tearing down Qt windows."""
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox


def close_test_window(window):
    # Production Close prompts are tested separately in test_qt_recovery.
    with patch("macro_qt.QMessageBox.question",
               return_value=QMessageBox.StandardButton.Discard):
        window.close()
