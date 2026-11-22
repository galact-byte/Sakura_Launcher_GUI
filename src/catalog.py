"""从官方元数据发现下载资产；失败时保留已有目录，不下载模型或后端。"""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import logging
import os
from pathlib import Path
import platform
import re
from urllib.parse import quote

import requests

from .common import GHPROXY_URL


MODELS_URL = "https://huggingface.co/api/models?author=SakuraLLM&filter=gguf&full=true&sort=lastModified&direction=-1&limit=100"
RELEASES_URL = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10"


def _get_json(url):
    urls = [url]
    if url.startswith("https://huggingface.co/"):
        urls.append(url.replace("https://huggingface.co/", "https://hf-mirror.com/", 1))
    elif url.startswith("https://api.github.com/"):
        urls.append(f"https://{GHPROXY_URL}/" + url)
    for index, endpoint in enumerate(urls):
        try:
            response = requests.get(endpoint, timeout=(4, 12))
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if index == len(urls) - 1:
                raise


def models_from_details(details, previous):
    known = {(row.get("repo", "").removeprefix("SakuraLLM/"), row["filename"]): row for row in previous}
    rows = []
    for detail in details:
        repo = detail.get("id", "")
        if not re.fullmatch(r"SakuraLLM/[\w.-]+", repo):
            continue
        for item in detail.get("siblings", []):
            name = item.get("rfilename", "")
            digest = item.get("lfs", {}).get("sha256", "")
            size = item.get("size", 0)
            if (not name.lower().endswith(".gguf") or re.search(r'[<>:"/\\|?*]', name)
                    or re.search(r"-\d{5}-of-\d{5}\.gguf$", name, re.I)
                    or not re.fullmatch(r"[a-fA-F0-9]{64}", digest)
                    or not isinstance(size, (int, float)) or size <= 0):
                continue
            row = copy.deepcopy(known.get((repo.removeprefix("SakuraLLM/"), name), {}))
            row.update(repo=repo, filename=name, sha256=digest, size=round(size / 10**9, 2))
            # 下载元数据不足以推导显存阈值，不给新模型编造推荐参数。
            for key, value in {"minimal_gpu_memory_gib": 0, "recommended_np": {},
                               "base_model_hf": None, "bpw": None, "config_cache": None}.items():
                row.setdefault(key, value)
            rows.append(row)
    return rows


def _links(url):
    if not url.startswith("https://github.com/ggml-org/llama.cpp/releases/download/"):
        raise ValueError("发行资产地址不属于 llama.cpp 官方仓库")
    return {"GitHub": url, "GHProxy": f"https://{GHPROXY_URL}/" + url}


def backends_from_releases(releases, system, machine):
    releases = sorted((r for r in releases if not r.get("draft")),
                      key=lambda r: r.get("published_at", ""), reverse=True)
    arch = "arm64" if machine.lower() in ("arm64", "aarch64") else "x64"
    for release in releases:
        tag = release.get("tag_name", "")
        if not re.fullmatch(r"b\d+", tag):
            continue
        assets = {a["name"]: a for a in release.get("assets", [])}
        rows = []
        for name, asset in assets.items():
            prefix = f"llama-{tag}-bin-"
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix):]
            if system == "Windows":
                if not re.fullmatch(rf"win-(cuda-[\d.]+|rocm-[\d.]+|vulkan|cpu|hip-radeon)-{arch}\.zip", suffix):
                    continue
            elif system == "Darwin":
                if suffix not in (f"macos-{arch}.tar.gz", f"macos-{arch}.zip"):
                    continue
            else:
                continue
            links = _links(asset["browser_download_url"])
            runtime = None
            cuda = suffix.startswith("win-cuda-")
            if cuda:
                runtime_name = "cudart-llama-bin-" + suffix
                if runtime_name not in assets:
                    continue
                runtime = {"filename": runtime_name, "download_links": _links(assets[runtime_name]["browser_download_url"])}
            label = suffix.removesuffix(".tar.gz").removesuffix(".zip")
            backend = label.removeprefix("win-").removesuffix("-" + arch)
            if cuda:
                gpu = f"NVIDIA（{backend.upper()}，{arch}）"
            elif backend.startswith(("rocm-", "hip-")):
                gpu = f"AMD（{backend.upper()}，{arch}）"
            elif backend == "vulkan":
                gpu = f"Vulkan 设备（{arch}）"
            elif backend == "cpu":
                gpu = f"CPU（{arch}）"
            else:
                gpu = f"macOS（{arch}）"
            rows.append({"repo": f"ggml-org/llama.cpp/releases/download/{tag}",
                         "filename": name, "version": f"{tag}-{label}" + ("（预发布）" if release.get("prerelease") else ""),
                         "gpu": gpu, "require_cuda": cuda,
                         "download_links": links, "cudart": runtime})
        if rows:
            return rows
    return []


def refresh_catalog(previous, fetch_json=None, system=None, machine=None, cancelled=None):
    request = fetch_json or _get_json
    cancelled = cancelled or (lambda: False)
    result = copy.deepcopy(previous)
    messages = []
    if cancelled():
        return result, messages

    def fetch(url):
        if cancelled():
            raise RuntimeError("列表刷新已取消")
        return request(url)
    try:
        models = fetch(MODELS_URL)
        if not isinstance(models, list):
            raise ValueError("模型列表格式无效")
        repos = [m.get("id", "") for m in models if isinstance(m, dict)]
        repos = [r for r in repos if re.fullmatch(r"SakuraLLM/[\w.-]+", r)
                 and "korean" not in r.lower()]
        def load(repo):
            try:
                detail = fetch(f"https://huggingface.co/api/models/{quote(repo, safe='/')}?blobs=true")
                if not isinstance(detail, dict) or detail.get("id") != repo:
                    raise ValueError("模型元数据格式无效")
                return repo, detail
            except Exception as exc:
                return repo, exc
        details, failed = [], []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for repo, item in pool.map(load, repos):
                if isinstance(item, Exception):
                    failed.append(repo)
                    messages.append(f"{repo} 更新失败，保留已有条目")
                else:
                    details.append(item)
        rows = models_from_details(details, previous.get("sakura", []))
        if not rows:
            raise ValueError("未获取到可校验的单文件 GGUF，保留已有列表")
        rows += [row for row in previous.get("sakura", [])
                 if "SakuraLLM/" + row.get("repo", "").removeprefix("SakuraLLM/") in failed]
        result["sakura"] = rows
    except Exception as exc:
        messages.append(f"模型列表更新失败：{exc}")
    try:
        releases = fetch(RELEASES_URL)
        if not isinstance(releases, list):
            raise ValueError("发行列表格式无效")
        rows = backends_from_releases(releases, system or platform.system(), machine or platform.machine())
        if not rows:
            raise ValueError("没有匹配当前平台的完整发行资产，保留已有列表")
        result["llamacpp"] = rows
    except Exception as exc:
        messages.append(f"llama.cpp 列表更新失败：{exc}")
    return result, messages


def read_cache(path, bundled):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(isinstance(data.get(key), list) for key in ("sakura", "llamacpp")):
            raise ValueError("目录缓存格式无效")
        for row in data["sakura"]:
            required = {"repo", "filename", "sha256", "size", "minimal_gpu_memory_gib", "recommended_np", "base_model_hf", "bpw", "config_cache"}
            if not isinstance(row, dict) or not required.issubset(row):
                raise ValueError("模型缓存条目无效")
        for row in data["llamacpp"]:
            if not isinstance(row, dict) or not {"repo", "filename", "version", "gpu", "require_cuda"}.issubset(row):
                raise ValueError("后端缓存条目无效")
        return data
    except (OSError, ValueError, TypeError) as exc:
        logging.info("使用内置下载目录：%s", exc)
        return copy.deepcopy(bundled)


def write_cache(path, data):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
