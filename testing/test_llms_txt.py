from __future__ import annotations

import unittest
from pathlib import Path


class LlmManifestTests(unittest.TestCase):
    def test_llms_txt_exists(self) -> None:
        path = Path("llms.txt")
        self.assertTrue(path.exists(), "llms.txt must exist at project root")
        self.assertTrue(path.is_file(), "llms.txt must be a file")

    def test_llms_txt_has_expected_sections(self) -> None:
        text = Path("llms.txt").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# "), "llms.txt should start with an H1 heading")
        self.assertIn("## Docs", text)
        self.assertIn("## Core API", text)


if __name__ == "__main__":
    unittest.main()
