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

    def test_download_directory_picker_persists_choice_and_cancel_preserves_it(self):
        from src.section_settings import SettingsSection
        from src.setting import SETTING
        import tempfile
        from pathlib import Path
        import src.setting as setting_module
        with tempfile.TemporaryDirectory() as folder, patch.object(SettingsSection, "check_launcher_update"), patch.object(setting_module, "CONFIG_FILE", str(Path(folder) / "config.json")), patch.object(SETTING, "download_path", ""):
            widget = SettingsSection("settings-path-test")
            try:
                with patch("src.section_settings.QFileDialog.getExistingDirectory", return_value=folder):
                    widget.choose_download_path()
                self.assertEqual(SETTING.download_path, folder)
                import json
                saved = json.loads(Path(setting_module.CONFIG_FILE).read_text(encoding="utf-8"))
                self.assertEqual(saved["download_path"], folder)
                with patch("src.section_settings.QFileDialog.getExistingDirectory", return_value=""):
                    widget.choose_download_path()
                self.assertEqual(SETTING.download_path, folder)
            finally:
                logging.getLogger().removeHandler(widget.handler)
                widget.close()
                widget.deleteLater()
                self.app.processEvents()

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
