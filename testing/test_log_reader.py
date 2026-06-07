from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.log_reader import read_log_tail, resolve_log_file


class LogReaderTests(unittest.TestCase):
    def test_resolve_log_file_blocks_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                resolve_log_file(tmpdir, "../etc/passwd")

    def test_resolve_log_file_blocks_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                resolve_log_file(tmpdir, "/var/log/syslog")

    def test_resolve_log_file_accepts_child_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "app"
            log_dir.mkdir()
            log_file = log_dir / "service.log"
            log_file.write_text("line1\n", encoding="utf-8")

            resolved = resolve_log_file(tmpdir, "app/service.log")
            self.assertEqual(resolved, log_file.resolve())

    def test_read_log_tail_respects_max_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "service.log"
            file_path.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

            content, truncated = read_log_tail(file_path, max_bytes=1024, max_lines=3)
            self.assertEqual(content, "c\nd\ne")
            self.assertTrue(truncated)

    def test_read_log_tail_respects_max_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "service.log"
            file_path.write_text("0123456789" * 200, encoding="utf-8")

            content, truncated = read_log_tail(file_path, max_bytes=100, max_lines=200)
            self.assertLessEqual(len(content.encode("utf-8")), 100)
            self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
