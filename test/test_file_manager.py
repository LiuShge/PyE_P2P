from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.explorer_core.file_manager import (
    DirectoryHandle,
    DirectoryNotFoundError,
    FileHandle,
    FileManager,
)


class FileManagerTests(unittest.TestCase):
    def test_file_handle_read_write_and_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.txt"
            path.write_text("hello", encoding="utf-8")

            handle = FileHandle(path)
            self.assertEqual(handle.read_text(), "hello")
            handle.write_text(" world", append=True)
            self.assertEqual(handle.read_text(), "hello world")
            self.assertGreater(handle.size(), 0)

            renamed = handle.rename("renamed.txt")
            self.assertTrue(renamed.exists())
            handle.delete()
            self.assertFalse(renamed.exists())

    def test_file_handle_base64_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "binary.txt"
            path.write_bytes(b"abc")

            handle = FileHandle(path)
            encoded = handle.read_text(as_base64=True)
            self.assertEqual(encoded, "YWJj")

            handle.write_text(encoded, append=True, from_base64=True)
            self.assertEqual(handle.read_text(), "abcabc")

    def test_directory_handle_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "visible.txt").write_text("x", encoding="utf-8")
            hidden_dir = root / ".hidden"
            hidden_dir.mkdir()
            (hidden_dir / "secret.txt").write_text("secret", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "target.md").write_text("target", encoding="utf-8")

            directory = DirectoryHandle(root)
            self.assertIn("visible.txt", directory.list_entries())
            self.assertTrue(directory.contains("nested"))
            self.assertTrue(directory.create_directory("new_dir"))
            self.assertTrue(directory.create_file("new_file.txt"))

            opened = directory.open_file("visible.txt")
            self.assertEqual(opened.read_text(), "x")

            found = FileManager.search_files(root, "target.md", max_depth=3)
            self.assertEqual(found, [str(nested / "target.md")])

            found_without_ext = FileManager.search_files(root, "target", max_depth=3, ignore_extension=True)
            self.assertEqual(found_without_ext, [str(nested / "target.md")])

    def test_search_and_strip_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.txt").write_text("x", encoding="utf-8")
            self.assertEqual(FileManager.find_file(root, "a.txt"), str(root / "a.txt"))
            with self.assertRaises(FileNotFoundError):
                FileManager.search_files(root, "missing.txt", max_depth=1)

        with self.assertRaises(ValueError):
            FileManager.strip_extension()
        with self.assertRaises(ValueError):
            FileManager.strip_extension(path=Path("a"), name="a")

    def test_directory_not_found(self) -> None:
        with self.assertRaises(DirectoryNotFoundError):
            DirectoryHandle(Path("/definitely/not/a/real/path"))


if __name__ == "__main__":
    unittest.main()
