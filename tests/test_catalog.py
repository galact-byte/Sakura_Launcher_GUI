import copy
import json
from pathlib import Path
import tempfile
import unittest

from src import catalog


MODEL = {
    "id": "SakuraLLM/GalTransl-v4-4B-2601",
    "siblings": [
        {"rfilename": "new.gguf", "size": 3306256992, "lfs": {"sha256": "a" * 64}},
        {"rfilename": "README.md", "size": 10},
        {"rfilename": "part-00001-of-00002.gguf", "size": 100, "lfs": {"sha256": "b" * 64}},
        {"rfilename": "../bad.gguf", "size": 100, "lfs": {"sha256": "b" * 64}},
    ],
}


def asset(name):
    return {"name": name, "browser_download_url": "https://github.com/ggml-org/llama.cpp/releases/download/b12633/" + name}


RELEASE = {
    "tag_name": "b12633", "published_at": "2026-11-22T14:53:42Z", "draft": False, "prerelease": False,
    "assets": [
        asset("llama-b12633-bin-win-cuda-12.4-x64.zip"),
        asset("cudart-llama-bin-win-cuda-12.4-x64.zip"),
        asset("llama-b12633-bin-win-cuda-13.5-x64.zip"),
        asset("cudart-llama-bin-win-cuda-13.5-x64.zip"),
        asset("llama-b12633-bin-win-cuda-13.5-arm64.zip"),
        asset("llama-b12633-bin-win-vulkan-x64.zip"),
        asset("llama-b12633-bin-macos-arm64.tar.gz"),
    ],
}


class CatalogTests(unittest.TestCase):
    def test_models_use_api_size_hash_and_safe_complete_gguf_only(self):
        models = catalog.models_from_details([MODEL], [])
        self.assertEqual([m["filename"] for m in models], ["new.gguf"])
        self.assertEqual(models[0]["sha256"], "a" * 64)
        self.assertEqual(models[0]["size"], 3.31)
        self.assertIsNone(models[0]["bpw"])
        self.assertIsNone(models[0]["config_cache"])

    def test_existing_verified_resource_metadata_is_preserved(self):
        previous = [{"repo": MODEL["id"], "filename": "new.gguf", "bpw": 4.25, "config_cache": {"hidden_size": 4096}}]
        self.assertEqual(catalog.models_from_details([MODEL], previous)[0]["bpw"], 4.25)

    def test_missing_hash_never_becomes_a_downloadable_model(self):
        detail = copy.deepcopy(MODEL)
        detail["siblings"] = [{"rfilename": "nohash.gguf", "size": 100}]
        self.assertEqual(catalog.models_from_details([detail], []), [])

    def test_windows_backends_pair_exact_cuda_runtime_and_filter_arch(self):
        rows = catalog.backends_from_releases([RELEASE], "Windows", "AMD64")
        self.assertEqual(len(rows), 3)
        cuda = [row for row in rows if row["require_cuda"]]
        self.assertEqual([r["cudart"]["filename"] for r in cuda], [
            "cudart-llama-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-13.5-x64.zip"
        ])
        self.assertNotIn("arm64", " ".join(row["filename"] for row in rows))

    def test_newest_build_is_selected_instead_of_pinned_latest_release(self):
        old = copy.deepcopy(RELEASE)
        old["tag_name"] = "v1.0.0"
        old["published_at"] = "2026-11-13T10:20:19Z"
        rows = catalog.backends_from_releases([old, RELEASE], "Windows", "AMD64")
        self.assertTrue(all(row["version"].startswith("b12633") for row in rows))

    def test_draft_is_not_selected(self):
        draft = copy.deepcopy(RELEASE)
        draft.update(draft=True, published_at="2027-01-01T00:00:00Z")
        self.assertEqual(
            catalog.backends_from_releases([draft, RELEASE], "Windows", "AMD64"),
            catalog.backends_from_releases([RELEASE], "Windows", "AMD64"),
        )

    def test_official_numbered_nightly_is_listed_and_labeled(self):
        nightly = copy.deepcopy(RELEASE)
        nightly["prerelease"] = True
        rows = catalog.backends_from_releases([nightly], "Windows", "AMD64")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("预发布" in row["version"] for row in rows))

    def test_mac_backend_uses_real_tar_asset(self):
        rows = catalog.backends_from_releases([RELEASE], "Darwin", "arm64")
        self.assertEqual([r["filename"] for r in rows], ["llama-b12633-bin-macos-arm64.tar.gz"])

    def test_current_rocm_bundle_is_discovered_for_amd(self):
        release = copy.deepcopy(RELEASE)
        release["assets"] = [asset("llama-b12633-bin-win-rocm-10.0-x64.zip")]
        rows = catalog.backends_from_releases([release], "Windows", "AMD64")
        self.assertEqual(len(rows), 1)
        self.assertIn("AMD", rows[0]["gpu"])

    def test_unpaired_cuda_runtime_is_not_offered(self):
        release = copy.deepcopy(RELEASE)
        release["assets"] = [release["assets"][0]]
        self.assertEqual(catalog.backends_from_releases([release], "Windows", "AMD64"), [])

    def test_remote_failure_preserves_previous_catalog(self):
        previous = {"sakura": [{"filename": "old.gguf"}], "llamacpp": [{"filename": "old.zip"}]}
        def fail(url):
            raise OSError("offline")
        result, messages = catalog.refresh_catalog(previous, fail, "Windows", "AMD64")
        self.assertEqual(result, previous)
        self.assertTrue(messages)

    def test_partial_failure_does_not_erase_working_backend_list(self):
        previous = {"sakura": [{"filename": "old.gguf"}], "llamacpp": []}
        def fetch(url):
            if "api.github.com" in url:
                return [RELEASE]
            raise OSError("HF unavailable")
        result, messages = catalog.refresh_catalog(previous, fetch, "Windows", "AMD64")
        self.assertEqual(result["sakura"], previous["sakura"])
        self.assertEqual(len(result["llamacpp"]), 3)
        self.assertTrue(messages)

    def test_successful_model_discovery_preserves_old_rows_if_one_repo_fails(self):
        previous = {"sakura": [{"repo": "SakuraLLM/old", "filename": "old.gguf"}], "llamacpp": []}
        def fetch(url):
            if "/api/models?" in url:
                return [{"id": MODEL["id"]}, {"id": "SakuraLLM/old"}]
            if MODEL["id"] in url:
                return MODEL
            if "api.github.com" in url:
                return [RELEASE]
            raise OSError("one repo unavailable")
        result, messages = catalog.refresh_catalog(previous, fetch, "Windows", "AMD64")
        self.assertEqual({m["filename"] for m in result["sakura"]}, {"new.gguf", "old.gguf"})
        self.assertTrue(messages)

    def test_corrupt_cache_falls_back_to_bundled_data(self):
        bundled = {"sakura": [], "llamacpp": []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(catalog.read_cache(path, bundled), bundled)
            path.write_text(json.dumps({"sakura": "bad", "llamacpp": []}), encoding="utf-8")
            self.assertEqual(catalog.read_cache(path, bundled), bundled)

    def test_cancelled_refresh_makes_no_network_requests(self):
        previous = {"sakura": [], "llamacpp": []}
        def unexpected_fetch(url):
            self.fail("取消后不应请求网络")
        result, messages = catalog.refresh_catalog(previous, unexpected_fetch, cancelled=lambda: True)
        self.assertEqual(result, previous)

    def test_cache_round_trip(self):
        data = {"sakura": [], "llamacpp": []}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            catalog.write_cache(path, data)
            self.assertEqual(catalog.read_cache(path, {}), data)
            self.assertFalse(path.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
