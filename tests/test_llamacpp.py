import subprocess
import unittest
from unittest.mock import patch

from src import llamacpp


class VersionTests(unittest.TestCase):
    def test_recognizes_build_number_in_semantic_version_output(self):
        result = subprocess.CompletedProcess(
            [], 0, "", "version: 1.0.0-dev (build 12633, commit 9c10c94e1)\n"
        )
        with patch.object(llamacpp.subprocess, "run", return_value=result):
            self.assertEqual(llamacpp.get_llamacpp_version("backend"), 12633)

    def test_accepts_legacy_version_on_either_output_stream(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                result = subprocess.CompletedProcess([], 0, "", "")
                setattr(result, stream, "version: 5391 (b2838049)\n")
                with patch.object(llamacpp.subprocess, "run", return_value=result):
                    self.assertEqual(llamacpp.get_llamacpp_version("backend"), 5391)

    def test_unknown_semantic_version_does_not_become_build_one(self):
        result = subprocess.CompletedProcess([], 0, "", "version: 1.0.0\n")
        with patch.object(llamacpp.subprocess, "run", return_value=result):
            self.assertIsNone(llamacpp.get_llamacpp_version("backend"))

    def test_failed_probe_does_not_report_version(self):
        result = subprocess.CompletedProcess([], 1, "", "version: 5391\n")
        with patch.object(llamacpp.subprocess, "run", return_value=result):
            self.assertIsNone(llamacpp.get_llamacpp_version("backend"))


class OptionTests(unittest.TestCase):
    def options(self, help_text, flash=True, no_mmap=True):
        result = subprocess.CompletedProcess([], 0, help_text, "")
        with patch.object(llamacpp.subprocess, "run", return_value=result):
            return llamacpp.get_llamacpp_extra_options("backend", flash, no_mmap)

    def test_new_backend_receives_explicit_flash_and_load_mode(self):
        self.assertEqual(
            self.options("-fa, --flash-attn [on|off|auto]\n-lm, --load-mode MODE\n"),
            ["-fa", "on", "--load-mode", "none"],
        )

    def test_old_backend_retains_boolean_flags(self):
        self.assertEqual(
            self.options("-fa, --flash-attn enable Flash Attention\n--no-mmap disable mmap\n"),
            ["-fa", "--no-mmap"],
        )

    def test_intermediate_backend_uses_explicit_flash_and_old_mmap(self):
        self.assertEqual(
            self.options("-fa, --flash-attn [on|off|auto]\n--no-mmap disable mmap\n"),
            ["-fa", "on", "--no-mmap"],
        )

    def test_disabled_checkboxes_add_no_options(self):
        self.assertEqual(self.options("", False, False), [])

    def test_unsupported_options_are_not_invented(self):
        self.assertEqual(self.options("--model FNAME\n"), [])

    def test_help_can_be_written_to_stderr(self):
        result = subprocess.CompletedProcess([], 0, "", "--flash-attn [on|off|auto]\n")
        with patch.object(llamacpp.subprocess, "run", return_value=result):
            self.assertEqual(
                llamacpp.get_llamacpp_extra_options("backend", True, False),
                ["-fa", "on"],
            )

    def test_probe_failure_omits_optional_flags_instead_of_crashing(self):
        for failure in (OSError("missing"), subprocess.TimeoutExpired("backend", 5)):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(llamacpp.subprocess, "run", side_effect=failure):
                    self.assertEqual(
                        llamacpp.get_llamacpp_extra_options("backend", True, True), []
                    )

    def test_nonzero_help_exit_does_not_generate_options(self):
        result = subprocess.CompletedProcess([], 1, "--no-mmap", "")
        with patch.object(llamacpp.subprocess, "run", return_value=result):
            self.assertEqual(
                llamacpp.get_llamacpp_extra_options("backend", False, True), []
            )


if __name__ == "__main__":
    unittest.main()
