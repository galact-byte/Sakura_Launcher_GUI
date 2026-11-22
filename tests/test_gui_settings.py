import importlib.util
import logging
import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("qfluentwidgets"), "完整 Qt 交互测试由远端依赖环境执行")
class GuiSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_log_view_displays_emitted_message(self):
        from PySide6.QtWidgets import QTextEdit
        from src.section_settings import SettingsSection

        root = logging.getLogger()
        level = root.level
        with patch.object(SettingsSection, "check_launcher_update"):
            widget = SettingsSection("settings-test")
        try:
            logging.getLogger("sakura-regression").warning("LOG-VIEW-REGRESSION")
            self.app.processEvents()
            displays = [child for child in widget.findChildren(QTextEdit) if child.isReadOnly()]
            self.assertTrue(any("LOG-VIEW-REGRESSION" in child.toPlainText() for child in displays))
        finally:
            root.removeHandler(widget.handler)
            root.setLevel(level)
            widget.close()
            widget.deleteLater()
            self.app.processEvents()
