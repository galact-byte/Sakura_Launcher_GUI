import os
from pathlib import Path
import tempfile
import unittest

from src import common, setting


class PortablePathTests(unittest.TestCase):
    def test_config_path_is_bound_to_launcher_directory(self):
        self.assertTrue(os.path.isabs(setting.CONFIG_FILE))
        self.assertEqual(Path(setting.CONFIG_FILE).parent, Path(common.CURRENT_DIR))

    def test_source_resources_do_not_depend_on_working_directory(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                self.assertEqual(Path(common.get_resource_path("data.json")), Path(common.CURRENT_DIR) / "data.json")
                self.assertTrue(Path(common.get_resource_path("data.json")).is_file())
            finally:
                os.chdir(previous)
