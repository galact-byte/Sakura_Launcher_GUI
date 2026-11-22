import unittest

from src.llamacpp import LlamacppList
from src.sakura import Sakura


class CatalogAdapterTests(unittest.TestCase):
    def test_backend_keeps_selected_release_runtime(self):
        runtime = {"filename": "cudart-llama-bin-win-cuda-13.5-x64.zip", "download_links": {"GitHub": "https://example.test/runtime.zip"}}
        listing = LlamacppList()
        listing.update_llamacpp_list({"llamacpp": [{
            "repo": "ggml-org/llama.cpp/releases/download/b12633",
            "filename": "new.zip", "version": "b12633", "gpu": "CUDA 13.5",
            "require_cuda": True, "cudart": runtime,
            "download_links": {"GitHub": "https://example.test/new.zip"},
        }]})
        row = next(iter(listing))
        self.assertEqual(row.cudart, runtime)
        self.assertEqual(row.download_links["GitHub"], "https://example.test/new.zip")

    def model(self, repo):
        return Sakura(repo, "new.gguf", "a" * 64, 3.31, 0, {}, None, None, None)

    def test_model_links_do_not_duplicate_organization(self):
        for repo in ["SakuraLLM/GalTransl-v4-4B-2601", "GalTransl-v4-4B-2601"]:
            with self.subTest(repo=repo):
                self.assertEqual(self.model(repo).download_links["HuggingFace"],
                                 "https://huggingface.co/SakuraLLM/GalTransl-v4-4B-2601/resolve/main/new.gguf")

    def test_unknown_model_memory_metadata_does_not_invent_estimate(self):
        with self.assertRaises(ValueError):
            self.model("GalTransl-v4-4B-2601").to_model_config()
