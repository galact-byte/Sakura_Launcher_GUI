import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("qfluentwidgets"), "完整 Qt 交互测试由远端依赖环境执行")
class GuiCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from src import section_download
        self.module = section_download
        self.temporary = tempfile.TemporaryDirectory()
        self.directory_patch = patch.object(section_download, "CURRENT_DIR", self.temporary.name)
        self.refresh_patch = patch.object(section_download.DownloadSection, "start_catalog_refresh")
        self.directory_patch.start()
        self.refresh_patch.start()
        self.widget = section_download.DownloadSection("download-test")
        path = Path(__file__).resolve().parents[1] / "data.json"
        self.bundled = json.loads(path.read_text(encoding="utf-8"))

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()
        self.refresh_patch.stop()
        self.directory_patch.stop()
        self.temporary.cleanup()

    def test_shorter_refresh_removes_stale_model_and_backend_rows(self):
        data = dict(self.bundled)
        data["sakura"] = data["sakura"][:2]
        data["llamacpp"] = data["llamacpp"][:2]
        self.widget.apply_catalog(data, "first")
        data["sakura"] = data["sakura"][:1]
        data["llamacpp"] = data["llamacpp"][:1]
        self.widget.apply_catalog(data, "updated")
        self.assertEqual(self.widget.sakura_table.rowCount(), 1)
        self.assertEqual(self.widget.llamacpp_table.rowCount(), 1)
        self.assertTrue(all(label.text() == "updated" for label in self.widget.catalog_labels))

    def test_switching_download_source_updates_button_availability(self):
        data = dict(self.bundled)
        row = dict(data["llamacpp"][0])
        row["download_links"] = {"GitHub": "https://github.com/example/archive.zip"}
        data["llamacpp"] = [row]
        self.widget.apply_catalog(data, "updated")
        self.widget.llamacpp_download_src = "GHProxy"
        self.widget.refresh_llamacpp_table()
        self.assertFalse(self.widget.llamacpp_table.cellWidget(0, 2).isEnabled())
        self.widget.llamacpp_download_src = "GitHub"
        self.widget.refresh_llamacpp_table()
        self.assertTrue(self.widget.llamacpp_table.cellWidget(0, 2).isEnabled())

    def test_worker_reports_unexpected_failure_and_finishes(self):
        worker = self.module.LoadDataThread(self.bundled, Path(self.temporary.name) / "cache.json", self.widget)
        results, finished = [], []
        worker.sig_loaded.connect(lambda *args: results.append(args))
        worker.finished.connect(lambda: finished.append(True))
        with patch.object(self.module, "refresh_catalog", side_effect=ValueError("bad metadata")):
            with self.assertLogs(level="ERROR"):
                worker.run()
        self.assertEqual(results[0][0], self.bundled)
        self.assertIn("失败", results[0][1])
        self.assertEqual(finished, [True])

    def test_cancel_button_stops_worker_and_marks_task(self):
        from qfluentwidgets import PushButton
        from src.setting import SETTING
        task = self.module.DownloadTask("test model", "https://example.com/model.gguf", "model.gguf")
        with patch.object(SETTING, "download_path", self.temporary.name), patch.object(self.module.DownloadThread, "start"):
            self.widget._start_download_task(task, lambda: None)
        worker = self.widget.download_threads[-1]
        button = next(button for button in self.widget.findChildren(PushButton) if button.text() == "取消下载")
        button.click()
        self.assertTrue(worker.cancelled.is_set())
        self.assertEqual(task.state, self.module.DownloadTaskState.ERROR)
        self.assertFalse(button.isEnabled())

    def test_selected_download_directory_is_used_for_model_and_checksum(self):
        from types import SimpleNamespace
        from src.setting import SETTING
        target = Path(self.temporary.name) / "selected models"
        model = SimpleNamespace(filename="model.gguf", sha256="a" * 64,
                                download_links={self.widget.sakura_download_src: "https://example.com/model.gguf"})
        with patch.object(SETTING, "download_path", str(target), create=True), patch.object(self.module.DownloadThread, "start"):
            self.widget.start_download_sakura(model)
        worker = self.widget.download_threads[-1]
        self.assertEqual(Path(worker.filename), target / "model.gguf")
        self.assertEqual(worker.expected_sha256, "a" * 64)
        self.widget.download_tasks.clear()

    def test_cuda_download_uses_runtime_attached_to_selected_backend(self):
        from src.llamacpp import Llamacpp
        runtime = {"filename": "cuda13.zip", "download_links": {"GitHub": "https://github.com/example/cuda13.zip"}}
        backend = Llamacpp("example", "backend.zip", "b12633", "CUDA13", True, cudart=runtime)
        with patch.object(self.widget, "_start_download_task") as start, patch.object(self.widget, "start_download_cudart") as cudart:
            self.widget.start_download_llamacpp(backend)
        self.assertEqual(start.call_count, 1)
        cudart.assert_called_once_with(runtime)
