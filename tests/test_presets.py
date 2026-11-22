import ast
from pathlib import Path
import unittest


def load_reorder_methods():
    # 仅隔离 Qt 表格边界，执行源文件中的原始排序方法；本地无需安装 GUI 依赖。
    path = Path(__file__).resolve().parents[1] / "src" / "section_settings.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    editor = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ConfigEditor")
    names = {"move_to_top", "move_to_bottom", "move_up", "move_down", "move_to"}
    methods = [node for node in editor.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {}
    module = ast.Module(body=methods, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


class PresetTable:
    locals().update(load_reorder_methods())

    def __init__(self):
        self.rows = ["first", "second", "third"]
        self.selected = None

    def swap_rows(self, first, second):
        self.rows[first], self.rows[second] = self.rows[second], self.rows[first]

    def selectRow(self, row):
        self.selected = row

    def rowCount(self):
        return len(self.rows)


class PresetTests(unittest.TestCase):
    def test_long_press_moves_selected_preset_to_top(self):
        table = PresetTable()
        table.move_to_top(2)
        self.assertEqual(table.rows, ["third", "first", "second"])
        self.assertEqual(table.selected, 0)

    def test_top_preset_stays_at_top(self):
        table = PresetTable()
        table.move_to_top(0)
        self.assertEqual(table.rows, ["first", "second", "third"])

    def test_bottom_and_single_step_moves_keep_existing_behavior(self):
        for method, row, expected in [
            ("move_to_bottom", 0, ["second", "third", "first"]),
            ("move_up", 1, ["second", "first", "third"]),
            ("move_down", 1, ["first", "third", "second"]),
        ]:
            with self.subTest(method=method):
                table = PresetTable()
                getattr(table, method)(row)
                self.assertEqual(table.rows, expected)


if __name__ == "__main__":
    unittest.main()
