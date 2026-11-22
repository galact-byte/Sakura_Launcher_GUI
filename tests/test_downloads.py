import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from src.downloads import download_file


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<html>proxy error</html>' if self.path == '/html' else b'GGUFtest-model'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body) + (20 if self.path == '/short' else 0)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_success_creates_selected_directory_and_verifies_model(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'selected directory' / 'model.gguf'
            progress = []
            download_file(self.url + '/ok', target, progress.append,
                          expected_sha256=hashlib.sha256(b'GGUFtest-model').hexdigest())
            self.assertEqual(target.read_bytes(), b'GGUFtest-model')
            self.assertEqual(progress[-1], 100)
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_html_response_does_not_replace_existing_model(self):
        self.check_failure('/html', b'original')

    def test_truncated_response_does_not_leave_final_or_partial_file(self):
        self.check_failure('/short', None)

    def test_checksum_failure_preserves_existing_file(self):
        self.check_failure('/ok', b'original', expected_sha256='0' * 64)

    def test_cancellation_preserves_existing_file(self):
        self.check_failure('/ok', b'original', cancelled=lambda: True)

    def check_failure(self, endpoint, existing, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'model.gguf'
            if existing is not None:
                target.write_bytes(existing)
            with self.assertRaises((OSError, ValueError)):
                download_file(self.url + endpoint, target, **kwargs)
            if existing is None:
                self.assertFalse(target.exists())
                self.assertEqual(list(Path(folder).iterdir()), [])
            else:
                self.assertEqual(target.read_bytes(), existing)
                self.assertEqual(list(Path(folder).iterdir()), [target])
