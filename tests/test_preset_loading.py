import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class Input:
    def __init__(self, value=""):
        self.stored = value

    def setPlainText(self, value): self.stored = value
    def setValue(self, value): self.stored = value
    def setCurrentText(self, value): self.stored = value
    def setText(self, value): self.stored = value
    def setChecked(self, value): self.stored = value
    def text(self): return self.stored
    def currentText(self): return self.stored
    def toPlainText(self): return self.stored
    def value(self): return self.stored
    def isChecked(self): return self.stored


def section_for(config):
    path = Path(__file__).resolve().parents[1] / "src/section_run_server.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    section = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RunServerSection")
    methods = [node for node in section.body if isinstance(node, ast.FunctionDef) and node.name in {"save_preset", "load_selected_preset"}]
    saved = {}
    setting = SimpleNamespace(presets=[{"name": "test", "config": config}], set_preset=lambda name, value: saved.update(value))
    namespace = {"SETTING": setting, "UiInfoBarSuccess": lambda *args: None}
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), str(path), "exec"), namespace)
    class Section:
        save_preset = namespace["save_preset"]
        load_selected_preset = namespace["load_selected_preset"]
        update_context_per_thread = lambda self: None
    instance = Section()
    for name in ["command_template", "gpu_layers_spinbox", "model_path", "context_length_input",
                 "n_parallel_spinbox", "host_input", "port_input", "flash_attention_check", "npp_input",
                 "ntg_input", "npl_input", "no_mmap_check", "llamacpp_override", "gpu_combo"]:
        setattr(instance, name, Input())
    instance.config_preset_combo = Input("test")
    return instance, saved


class PresetLoadingTests(unittest.TestCase):
    def test_existing_saved_template_is_restored_without_losing_widget(self):
        section, _ = section_for({"custom_command": "%cmd% --temp 0.2"})
        widget = section.command_template
        section.load_selected_preset()
        self.assertIs(section.command_template, widget)
        self.assertEqual(widget.toPlainText(), "%cmd% --temp 0.2")

    def test_legacy_extra_options_are_migrated(self):
        for config, expected in [
            ({"custom_command": "-c 4096"}, "%cmd_raw% -c 4096"),
            ({"custom_command_append": "--temp 0.2"}, "%cmd% --temp 0.2"),
        ]:
            with self.subTest(config=config):
                section, _ = section_for(config)
                section.load_selected_preset()
                self.assertEqual(section.command_template.toPlainText(), expected)

    def test_new_saved_template_uses_the_key_loader_reads(self):
        section, saved = section_for({})
        section.command_template.setPlainText('%cmd% --log-file "E:/logs/server log.txt"')
        section.save_preset()
        self.assertEqual(saved["command_template"], section.command_template.toPlainText())

    def test_host_and_port_are_restored_from_selected_preset(self):
        section, _ = section_for({"host": "127.0.0.2", "port": "8081"})
        section.load_selected_preset()
        self.assertEqual(section.host_input.text(), "127.0.0.2")
        self.assertEqual(section.port_input.text(), "8081")
