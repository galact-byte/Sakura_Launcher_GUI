from hashlib import sha256
import os
from pathlib import Path
import tempfile

import requests


def download_file(url, target, progress=None, expected_sha256=None, cancelled=None):
    """先校验暂存文件，成功后再替换目标，失败时保留原有文件。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + '.', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            if cancelled and cancelled():
                raise OSError('下载已取消')
            with requests.get(url, stream=True, timeout=(10, 30),
                              headers={'Accept-Encoding': 'identity'}) as response:
                response.raise_for_status()
                total = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                digest = sha256()
                for chunk in response.iter_content(256 * 1024):
                    if cancelled and cancelled():
                        raise OSError('下载已取消')
                    output.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if progress and total:
                        progress(min(99, downloaded * 100 // total))
                if not downloaded or (total and downloaded != total):
                    raise ValueError('下载内容不完整，请重试')
                if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
                    raise ValueError('文件 SHA-256 校验失败，请更换下载源后重试')
        with open(temporary, 'rb') as stream:
            signature = stream.read(4)
        name = target.name.lower()
        expected = b'GGUF' if name.endswith('.gguf') else (
            b'PK' if name.endswith('.zip') else (
                b'\x1f\x8b' if name.endswith('.tar.gz') else (
                    b'MZ' if name.endswith('.exe') else None)))
        if expected and not signature.startswith(expected):
            raise ValueError('下载内容不是预期文件，可能是代理或网站返回的错误页面')
        if cancelled and cancelled():
            raise OSError('下载已取消')
        os.replace(temporary, target)
        if progress:
            progress(100)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
