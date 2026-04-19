from __future__ import annotations

__all__ = [
    "FileManagerError",
    "DirectoryNotFoundError",
    "DirectoryCreationError",
    "FileCreationError",
    "FileHandle",
    "DirectoryHandle",
    "FileManager",
]

import base64
from collections import deque
from pathlib import Path
from typing import Iterable, Optional, Union


PathLike = Union[str, Path]


class FileManagerError(Exception):
    """Base class for file management errors."""


class DirectoryNotFoundError(FileManagerError, NotADirectoryError):
    def __init__(self, path: PathLike) -> None:
        self.path = str(path)
        super().__init__(f"Directory '{self.path}' does not exist or is not a directory.")


class DirectoryCreationError(FileManagerError, OSError):
    def __init__(self, path: PathLike) -> None:
        self.path = str(path)
        super().__init__(f"Unable to create directory '{self.path}'.")


class FileCreationError(FileManagerError, OSError):
    def __init__(self, path: PathLike) -> None:
        self.path = str(path)
        super().__init__(f"Unable to create file '{self.path}'.")


class FileHandle:
    """Operate on a single file."""

    def __init__(self, file_path: PathLike) -> None:
        self.path = Path(file_path)
        if not self.path.is_file():
            raise FileNotFoundError(f"File '{self.path}' does not exist.")

    def read_text(self, *, as_base64: bool = False) -> str:
        content = self.path.read_bytes()
        if as_base64:
            return base64.b64encode(content).decode("utf-8")
        return content.decode("utf-8", errors="replace")

    def read_lines(self, *, as_base64: bool = False) -> Iterable[str]:
        with self.path.open("rb") as handle:
            for line in handle:
                if as_base64:
                    yield base64.b64encode(line).decode("utf-8")
                else:
                    yield line.decode("utf-8", errors="replace")

    def write_text(self, content: str, *, append: bool = False, from_base64: bool = False) -> None:
        data = content.encode("utf-8")
        if from_base64:
            data = base64.b64decode(data)

        mode = "ab" if append else "wb"
        with self.path.open(mode) as handle:
            handle.write(data)

    def delete(self) -> None:
        self.path.unlink()

    def size(self) -> int:
        return self.path.stat().st_size

    def rename(self, new_name: str) -> Path:
        new_path = self.path.with_name(new_name)
        self.path.rename(new_path)
        self.path = new_path
        return self.path


class DirectoryHandle:
    """Operate on a single directory."""

    def __init__(self, directory_path: PathLike) -> None:
        self.path = Path(directory_path)
        if not self.path.is_dir():
            raise DirectoryNotFoundError(self.path)
        self._refresh_entries()

    def _refresh_entries(self) -> None:
        try:
            self.entries = [entry.name for entry in self.path.iterdir()]
        except (PermissionError, OSError):
            self.entries = []

    def refresh(self) -> list[str]:
        self._refresh_entries()
        return self.entries

    def list_entries(self) -> list[str]:
        self._refresh_entries()
        return self.entries

    def contains(self, name: str) -> bool:
        return (self.path / name).exists()

    def create_directory(self, name: str, *, allow_failure: bool = False) -> bool:
        target = self.path / name
        try:
            target.mkdir(parents=True, exist_ok=True)
            self._refresh_entries()
            return True
        except Exception as exc:
            if allow_failure:
                return False
            raise DirectoryCreationError(target) from exc

    def create_file(self, name: str, *, allow_failure: bool = False) -> bool:
        target = self.path / name
        try:
            if target.exists():
                raise FileExistsError(f"File '{target}' already exists.")
            target.touch()
            self._refresh_entries()
            return True
        except Exception as exc:
            if allow_failure:
                return False
            raise FileCreationError(target) from exc

    def open_file(self, name: str) -> FileHandle:
        return FileHandle(self.path / name)


class FileManager:
    """Static helper collection for file and directory operations."""

    @staticmethod
    def filter_entries(entries: list[Path], *, ignore_hidden: bool) -> list[Path]:
        filtered: list[Path] = []
        for entry in entries:
            try:
                is_valid = entry.is_dir() or entry.is_file()
            except (PermissionError, OSError):
                continue

            if not is_valid:
                continue
            if ignore_hidden and entry.name.startswith("."):
                continue
            filtered.append(entry)
        return filtered

    @staticmethod
    def strip_extension(*, path: PathLike | None = None, name: str | None = None) -> str:
        if (path is None and name is None) or (path is not None and name is not None):
            raise ValueError("exactly one of path or name must be provided")

        target = Path(path) if path is not None else Path(str(name))
        return str(target.with_suffix("")) if target.suffix else str(target)

    @staticmethod
    def find_file(
        root: PathLike,
        target_name: str,
        *,
        max_depth: int = 6,
        ignore_extension: bool = False,
        ignore_hidden: bool = True,
        ignore_permission: bool = True,
    ) -> str:
        results = FileManager.search_files(
            root,
            target_name,
            max_depth=max_depth,
            ignore_extension=ignore_extension,
            ignore_hidden=ignore_hidden,
            ignore_permission=ignore_permission,
            max_results=1,
        )
        return results[0]

    @staticmethod
    def search_files(
        root: PathLike,
        target_name: str,
        *,
        max_depth: int = 6,
        ignore_extension: bool = False,
        ignore_hidden: bool = True,
        ignore_permission: bool = True,
        max_results: Optional[int] = None,
    ) -> list[str]:
        root_path = Path(root)
        try:
            if not root_path.is_dir():
                raise DirectoryNotFoundError(root_path)
        except (PermissionError, OSError):
            if ignore_permission:
                return []
            raise

        target_key = (
            target_name
            if not ignore_extension
            else FileManager.strip_extension(name=target_name)
        )

        queue = deque([root_path])
        results: list[str] = []

        for _ in range(max_depth):
            if not queue:
                break

            next_queue: deque[Path] = deque()
            while queue:
                current_dir = queue.popleft()
                try:
                    entries = list(current_dir.iterdir())
                except (PermissionError, OSError):
                    if ignore_permission:
                        continue
                    raise

                for entry in FileManager.filter_entries(entries, ignore_hidden=ignore_hidden):
                    try:
                        if entry.is_dir():
                            next_queue.append(entry)
                            continue

                        entry_name = (
                            FileManager.strip_extension(name=entry.name)
                            if ignore_extension
                            else entry.name
                        )
                        if entry_name == target_key:
                            results.append(str(entry))
                            if max_results is not None and len(results) >= max_results:
                                return results
                    except (PermissionError, OSError):
                        continue

            queue = next_queue

        if not results:
            raise FileNotFoundError(f"No such file: '{target_name}' under '{root_path}'")

        return results


if __name__ == "__main__":
    root = "/"
    this_file = Path(__file__).name
    try:
        print(f"Searching for {this_file} in {root}...")
        print(FileManager.search_files(root, this_file, max_results=9))
    except Exception as exc:
        print(exc)
