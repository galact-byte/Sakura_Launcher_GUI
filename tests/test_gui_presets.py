import importlib.util
import os
import unittest


@unittest.skipUnless(importlib.util.find_spec("qfluentwidgets"), "完整 Qt 交互测试由远端依赖环境执行")
class GuiPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_long_press_up_button_moves_preset_to_top(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from src.section_settings import ConfigEditor

        table = ConfigEditor()
        try:
            table.set_config([
                {"name": "first", "config": {"port": "8080"}},
                {"name": "second", "config": {"port": "8081"}},
                {"name": "third", "config": {"port": "8082"}},
            ])
            table.show()
            self.app.processEvents()
            button = table.cellWidget(2, 1)
            QTest.mousePress(button, Qt.MouseButton.LeftButton)
            QTest.qWait(700)
            QTest.mouseRelease(button, Qt.MouseButton.LeftButton)
            self.assertEqual(
                [item["name"] for item in table.get_config()],
                ["third", "first", "second"],
            )
            self.assertEqual(table.get_config()[0]["config"], {"port": "8082"})
            self.assertEqual(table.currentRow(), 0)
        finally:
            table.close()
            table.deleteLater()
            self.app.processEvents()
