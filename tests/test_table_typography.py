import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TABLE_FONT_COMMANDS = re.compile(
    r"\\(?:tiny|scriptsize|footnotesize|small|normalsize|large)\b"
)


class TableTypographyTests(unittest.TestCase):
    def test_all_versioned_tables_use_the_shared_font_command(self):
        table_paths = sorted((REPOSITORY_ROOT / "paper_tables").rglob("*.tex"))
        self.assertTrue(table_paths)
        for table_path in table_paths:
            with self.subTest(table=table_path.relative_to(REPOSITORY_ROOT)):
                latex = table_path.read_text(encoding="utf-8")
                self.assertEqual(latex.count(r"\TableFont"), 1)
                self.assertIsNone(TABLE_FONT_COMMANDS.search(latex))

    def test_every_table_renderer_emits_the_shared_font_command(self):
        generator_paths = sorted((REPOSITORY_ROOT / "analysis").glob("*.py"))
        checked_renderers = 0
        for generator_path in generator_paths:
            source = generator_path.read_text(encoding="utf-8")
            table_count = source.count(r'"\begin{table')
            if not table_count:
                continue
            checked_renderers += table_count
            with self.subTest(generator=generator_path.name):
                self.assertEqual(source.count(r'"\TableFont"'), table_count)
                self.assertIsNone(TABLE_FONT_COMMANDS.search(source))
        self.assertGreater(checked_renderers, 0)


if __name__ == "__main__":
    unittest.main()
