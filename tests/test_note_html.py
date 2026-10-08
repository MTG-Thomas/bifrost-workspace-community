"""Ensure raw caller HTML cannot pass into a Halo note unchanged."""

import ast
from html import escape
from pathlib import Path
from types import SimpleNamespace
import unittest


class NoteHtmlTests(unittest.TestCase):
    def test_raw_html_is_escaped_before_markdown(self):
        source = Path(__file__).resolve().parents[1] / "shared/halopsa/tools/notes.py"
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_to_html")
        seen = []
        namespace = {
            "escape": escape,
            "markdown": SimpleNamespace(markdown=lambda text: seen.append(text) or text),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        result = namespace["_to_html"]('<p onclick="bad()">Hello</p>')
        self.assertEqual(result, '&lt;p onclick=&quot;bad()&quot;&gt;Hello&lt;/p&gt;')
        self.assertEqual(seen, [result])


if __name__ == "__main__":
    unittest.main()
