import logging
import os
import re
import subprocess
import sys
from typing import Dict, List
import zipfile

from PySide6.QtCore import QObject, Signal

from .common import GHPROXY_URL



class Llamacpp:
    repo: str
    filename: str
    version: str
    gpu: str
    require_cuda: bool
    download_links: Dict[str, str]

    def __init__(
        self,
        repo: str,
        filename: str,
        version: str,
        gpu: str,
        require_cuda: bool,
    ):
        self.repo = repo
        self.version = version
        self.gpu = gpu
        self.filename = filename
        self.require_cuda = require_cuda
        github_repo = f"https://github.com/{repo}/{filename}"
        self.download_links = {
            "GHProxy": f"https://{GHPROXY_URL}/" + github_repo,
            "GitHub": github_repo,
        }


class LlamacppList(QObject):
    DOWNLOAD_SRC = [
        "GHProxy",
        "GitHub",
    ]
    CUDART = {
        "filename": "cudart-llama-bin-win-cuda-12.4-x64.zip",
        "download_links": {
            "GitHub": "https://github.com/ggml-org/llama.cpp/releases/download/b6178/cudart-llama-bin-win-cuda-12.4-x64.zip",
            "GHProxy": f"https://{GHPROXY_URL}/https://github.com/ggml-org/llama.cpp/releases/download/b6178/cudart-llama-bin-win-cuda-12.4-x64.zip",
        },
    }
    _list: List[Llamacpp] = []
    changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

    def update_llamacpp_list(self, data_json):
        llamacpp_list = []
        for obj in data_json["llamacpp"]:
            llamacpp = Llamacpp(
                repo=obj["repo"],
                filename=obj["filename"],
                version=obj["version"],
                gpu=obj["gpu"],
                require_cuda=obj["require_cuda"],
            )
            llamacpp_list.append(llamacpp)
        self._list = llamacpp_list
        self.changed.emit(llamacpp_list)

    def __iter__(self):
        for item in self._list:
            yield item


LLAMACPP_LIST = LlamacppList()


def unzip_llamacpp(folder: str, filename: str):
    llama_folder = os.path.join(folder, "llama")
    file_path = os.path.join(folder, filename)
    print(f"将解压 {filename} 到 {llama_folder}")

    if not os.path.exists(llama_folder):
        os.mkdir(llama_folder)

    # 解压，如果文件已存在则覆盖
    if filename.endswith(".zip"):
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(llama_folder)
        # macOS build 中解压后产生的是'llama/build/bin'文件夹，需要将其中的所有内容移动到llama文件夹下
        if sys.platform == "darwin":
            bin_folder = os.path.join(llama_folder, "build", "bin")
            for item in os.listdir(bin_folder):
                src_path = os.path.join(bin_folder, item)
                dst_path = os.path.join(llama_folder, item)
                os.rename(src_path, dst_path)
                # 添加执行权限 (755 = rwxr-xr-x)
                os.chmod(dst_path, 0o755)
            # 删除空文件夹
            import shutil
            shutil.rmtree(os.path.join(llama_folder, "build"))
    else:
        print(f"不支持的文件格式: {filename}")
        return

    print(f"{filename} 已成功解压到 {llama_folder}")


def is_cudart_exist(folder: str):
    llama_folder = os.path.join(folder, "llama")
    for filename in [
        "cublas64_12.dll",
        "cublasLt64_12.dll",
        "cudart64_12.dll",
    ]:
        if not os.path.exists(os.path.join(llama_folder, filename)):
            return False
    return True


def get_llamacpp_version(llamacpp_path: str):
    exe_extension = ".exe" if sys.platform == "win32" else ""
    executable_path = os.path.join(llamacpp_path, f"llama-server{exe_extension}")
    try:
        logging.info(f"尝试执行命令: {executable_path} --version")
        result = subprocess.run(
            [executable_path, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            shell=os.name == "nt",
        )
        if result.returncode != 0:
            logging.warning("获取llama.cpp版本失败: %s", result.stderr)
            return None
        version_output = "\n".join((result.stdout, result.stderr)).strip()
        logging.info(f"版本输出: {version_output}")
        # 新版 version 为语义版本，参数兼容判断需要括号内的 build 编号。
        version_match = re.search(r"version:[^\r\n]*\bbuild\s+(\d+)\b", version_output)
        if not version_match:
            version_match = re.search(r"version:\s*(\d+)(?=\s|\(|$)", version_output)
        if version_match:
            return int(version_match.group(1))
        else:
            logging.info("无法匹配版本号")
    except subprocess.TimeoutExpired as e:
        logging.info(f"获取llama.cpp版本超时: {e.stdout}, {e.stderr}")
    except Exception as e:
        logging.info(f"获取llama.cpp版本时出错: {str(e)}")
    return None


def get_llamacpp_extra_options(llamacpp_path: str, flash_attention: bool, no_mmap: bool):
    if not (flash_attention or no_mmap):
        return []
    exe_extension = ".exe" if sys.platform == "win32" else ""
    executable_path = os.path.join(llamacpp_path, f"llama-server{exe_extension}")
    try:
        result = subprocess.run(
            [executable_path, "--help"], capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            logging.warning("无法检测llama.cpp参数，跳过可选参数: %s", result.stderr)
            return []
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.warning("无法检测llama.cpp参数，跳过可选参数: %s", exc)
        return []

    # 按实际帮助输出检测能力，避免给不同构建猜测参数变更版本。
    help_output = "\n".join((result.stdout, result.stderr))
    options = []
    if flash_attention:
        flash_option = re.search(r"--flash-attn\b[^\r\n]*", help_output)
        if flash_option:
            options.append("-fa")
            if re.search(r"\[(?:on|off|auto)\b", flash_option.group()):
                options.append("on")
        else:
            logging.warning("当前后端未声明Flash Attention参数，已跳过")
    if no_mmap:
        if "--load-mode" in help_output:
            options.extend(["--load-mode", "none"])
        elif "--no-mmap" in help_output:
            options.append("--no-mmap")
        else:
            logging.warning("当前后端未声明禁用内存映射参数，已跳过")
    return options
