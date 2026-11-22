import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from src.llamacpp import unzip_llamacpp


class BackendArchiveTests(unittest.TestCase):
    def test_tar_backend_directory_is_flattened_for_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "backend.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                entry = tarfile.TarInfo("llama-build/bin/llama-server")
                entry.size = 4
                entry.mode = 0o755
                archive.addfile(entry, io.BytesIO(b"test"))
            unzip_llamacpp(folder, path.name)
            self.assertEqual((Path(folder) / "llama/llama-server").read_bytes(), b"test")

    def test_zip_runtime_is_extracted_without_server(self):
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(Path(folder) / "runtime.zip", "w") as archive:
                archive.writestr("cudart64_12.dll", b"test")
            unzip_llamacpp(folder, "runtime.zip")
            self.assertTrue((Path(folder) / "llama/cudart64_12.dll").is_file())

    def test_archive_escape_is_rejected_before_touching_existing_backend(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "llama"
            destination.mkdir()
            (destination / "existing.dll").write_bytes(b"original")
            with zipfile.ZipFile(Path(folder) / "bad.zip", "w") as archive:
                archive.writestr("../escaped.txt", b"bad")
            with self.assertRaises(ValueError):
                unzip_llamacpp(folder, "bad.zip")
            self.assertEqual((destination / "existing.dll").read_bytes(), b"original")
            self.assertFalse((Path(folder) / "escaped.txt").exists())

    def test_unknown_format_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "bad.txt").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                unzip_llamacpp(folder, "bad.txt")
