from pathlib import Path
from typing import Iterable, List, Optional, Union
import base64
from collections import deque


class Explorer:
    """A static library dedicated solely to file operation-related functions."""
    
    class DirNotFoundError(NotADirectoryError):
        def __init__(self, path: str) -> None:
            self.path = str(path)
            self.message = f"Directory '{self.path}' does not exist or is not a directory."
            super().__init__(self.message)

        def __str__(self) -> str:
            return self.message

    class CanNotCreateDirError(NotADirectoryError):
        def __init__(self, path: str) -> None:
            self.path = str(path)
            self.message = f"Can not create directory '{self.path}'."
            super().__init__(self.message)

        def __str__(self) -> str:
            return self.message

    class CanNotCreateFileError(FileNotFoundError):
        def __init__(self, path: str) -> None:
            self.path = str(path)
            self.message = f"Can not create file '{self.path}'."
            super().__init__(self.message)

        def __str__(self) -> str:
            return self.message

    class ManageFile:
        """A class providing instance-based operations for a specific file."""
        def __init__(self, file_path: Union[str, Path]):
            """
                Initialize the ManageFile instance.
                param: file_path: the path of the file to manage
                raise: ValueError: if the file path is not a valid file
            """
            self.file_path = Path(file_path)
            if not self.file_path.is_file():
                raise ValueError(f"File {self.file_path} does not exist.")
        
        def read(self,
                 stream: bool = False,
                 base64code: bool = False) -> Union[str, Iterable]:
            """
                Read the content of the managed file.
                param: stream: whether to read the file as a stream (generator)
                param: base64code: whether to encode the content in base64
                return: the file content as a string or an iterable stream
            """
            if stream:
                return self._read_stream(base64code)
            
            content = self.file_path.read_bytes()
            if base64code:
                return base64.b64encode(content).decode('utf-8')
            return content.decode('utf-8', errors='ignore')

        def _read_stream(self, base64code: bool) -> Iterable[str]:
            """
                A private generator for reading file content line by line.
                param: base64code: whether to encode each line in base64
                return: a generator yielding lines of the file
            """
            with self.file_path.open('rb') as f:
                for line in f:
                    if base64code:
                        yield base64.b64encode(line).decode('utf-8')
                    else:
                        yield line.decode('utf-8', errors='ignore')

        def write(self, content: str,
                  append: bool = False,
                  base64code: bool = False):
            """
                Write or append data to the managed file.
                param: content: the string content to write
                param: append: whether to append to the file instead of overwriting
                param: base64code: whether to decode the content from base64 before writing
            """
            mode = 'ab' if append else 'wb'
            data = content.encode('utf-8')
            if base64code:
                data = base64.b64decode(data)
            
            with self.file_path.open(mode) as f:
                f.write(data)

        def delete(self):
            """
                Delete the managed file from the file system.
            """
            self.file_path.unlink()

        def get_size(self) -> int:
            """
                Get the size of the managed file.
                return: the size of the file in bytes
            """
            return self.file_path.stat().st_size

        def rename(self, new_name: str):
            """
                Rename the managed file.
                param: new_name: the new name for the file
            """
            new_path = self.file_path.parent / new_name
            self.file_path.rename(new_path)
            self.file_path = new_path
    
    class ManageFolder:
        """A class providing instance-based operations for a specific directory."""
        def __init__(self, dir_path: Union[str, Path]):
            """
                Initialize the ManageFolder instance.
                param: dir_path: the path of the directory to manage
                raise: DirNotFoundError: if the directory path does not exist
            """
            self.dir_path = Path(dir_path)
            if not self.dir_path.is_dir():
                raise Explorer.DirNotFoundError(str(dir_path))
            self.members = self.ls()

        def _update_mem(self):
            """
                Update the internal list of directory members.
            """
            try:
                self.members = [item.name for item in self.dir_path.iterdir()]
            except (PermissionError, OSError):
                self.members = []

        def ls(self) -> List[str]:
            """
                List all members within the managed directory.
                return: a list of names of files and folders in the directory
            """
            self._update_mem()
            return self.members

        def is_in(self, object_name: str) -> bool:
            """
                Check if a specific file or folder exists within the directory.
                param: object_name: the name of the object to search for
                return: True if the object exists, False otherwise
            """
            return (self.dir_path / object_name).exists()

        def new_folder(self, dir_name: str, allow_failure: bool = False) -> bool:
            """
                Create a new sub-folder within the managed directory.
                param: dir_name: the name of the new folder
                param: allow_failure: whether to return False on failure instead of raising an error
                return: True if creation succeeded, False if failed (and allowd_faild is True)
                raise: CanNotCreateDirError: if creation fails and allowd_faild is False
            """
            target_path = self.dir_path / dir_name
            try:
                target_path.mkdir(parents=True, exist_ok=True)
                self._update_mem()
                return True
            except Exception as e:
                if allow_failure:
                    return False
                raise Explorer.CanNotCreateDirError(str(target_path)) from e

        def new_file(self, file_name: str, allow_failure: bool = False) -> bool:
            """
                Create a new empty file within the managed directory.
                param: file_name: the name of the new file
                param: allow_failure: whether to return False on failure instead of raising an error
                return: True if creation succeeded, False if failed (and allowd_faild is True)
                raise: CanNotCreateFileError: if creation fails and allowd_faild is False
            """
            target_path = self.dir_path / file_name
            try:
                if target_path.exists():
                    raise FileExistsError(f"File {target_path} already exists.")
                target_path.touch()
                self._update_mem()
                return True
            except Exception as e:
                if allow_failure:
                    return False
                raise Explorer.CanNotCreateFileError(str(target_path)) from e

        def manage_file(self, file_name: str) -> 'Explorer.ManageFile':
            """
                Get a ManageFile instance for a file within this directory.
                param: file_name: the name of the file to manage
                return: a ManageFile instance for the specified file
                raise: ValueError: if the file does not exist
            """
            return Explorer.ManageFile(self.dir_path / file_name)

    @staticmethod
    def _filter_hid_objects(_ls_of_items: List[Path],
                            neglect_hid_file: bool) -> List[Path]:
        """
            Filter out hidden files or invalid paths from a list.
            param: _ls_of_items: list of Path objects to filter
            param: neglect_hid_file: whether to remove objects starting with '.'
            return: a filtered list of valid Path objects
        """
        filtered_ls = []
        for item in _ls_of_items:
            try:
                # Pathlib check can trigger PermissionError on system folders
                is_valid = item.is_dir() or item.is_file()
            except (PermissionError, OSError):
                continue

            if not is_valid:
                continue
            if neglect_hid_file and item.name.startswith('.'):
                continue
            filtered_ls.append(item)
        return filtered_ls

    @staticmethod
    def _remove_extension(file_path: Optional[Union[str, Path]] = None,
                          file_name: Optional[str] = None) -> str:
        """
            Remove the file extension from a path or filename string.
            param: file_path: the full path of the file
            param: file_name: the name of the file
            return: the string without the file extension
            raise: ValueError: if both parameters are provided or both are None
        """
        if (file_path and file_name) or (not file_path and not file_name):
            raise ValueError("file_path and file_name cannot be both None and both given")
        
        target = Path(file_path) if file_path else Path(str(file_name))
        return str(target.with_suffix('')) if target.suffix else str(target)

    @staticmethod
    def find_file(root_dir: Union[str, Path],
                  file_name: str,
                  loop_time: int = 6,
                  ignore_extension: bool = False, 
                  neglect_hid_file: bool = True,
                  ignore_permission: bool = True) -> str:
        """
            Get the file path of a file.
            param: root_dir: the root directory of the searching directories
            param: file_name: the file name which will be searched
            param: loop_time: how deep will be searched
            param: ignore_extension: whether to dis-exten the file
            param: neglect_hid_file: whether to neglect the hid file
            param: ignore_permission: Ignore permission issues and continue recursion
            return: the file path of the first file name appeared in the directory
            raise: FileNotFoundError: if the file is not found
                   Exception: if root_dir is not a directory
        """
        res = Explorer.search_file(root_dir, file_name, loop_time, ignore_extension, 
                                   neglect_hid_file, ignore_permission, max_result=1)
        return res[0]

    @staticmethod
    def search_file(root_dir: Union[str, Path],
                    file_name: str,
                    loop_time: int = 6,
                    ignore_extension: bool = False, 
                    neglect_hid_file: bool = True,
                    ignore_permission: bool = True,
                    max_result: Optional[int] = None) -> List[str]:
        """
            Get the file paths of all matching files.
            param: root_dir: the root directory of the searching directories
            param: file_name: the file name which will be searched
            param: loop_time: how deep will be searched
            param: ignore_extension: whether to dis-exten the file
            param: neglect_hid_file: whether to neglect the hid file
            param: ignore_permission: Ignore permission issues and continue recursion
            param: max_result: the maximum number of results to find before stopping
            return: a list of file paths for all matching files found within the depth limit
            raise: FileNotFoundError: if no matching file is found
                   Explorer.DirNotFoundError: if root_dir is not a directory
        """
        root_path = Path(root_dir)
        try:
            if not root_path.is_dir():
                raise Explorer.DirNotFoundError(str(root_dir))
        except (PermissionError, OSError):
            if ignore_permission: return []
            raise

        deep_dirs = deque([root_path])
        target_stem = file_name if not ignore_extension else Explorer._remove_extension(file_name=file_name)
        
        found_results = []
        for _ in range(loop_time):
            if not deep_dirs:
                break
                
            temp_deep_dir = []
            for current_dir in deep_dirs:
                try:
                    raw_members = list(current_dir.iterdir())
                except (PermissionError, OSError):
                    if ignore_permission:
                        continue
                    raise

                members = Explorer._filter_hid_objects(raw_members, neglect_hid_file)
                for item in members:
                    try:
                        if item.is_dir():
                            temp_deep_dir.append(item)
                        else:
                            compare_name = Explorer._remove_extension(file_name=item.name) if ignore_extension else item.name
                            if target_stem == compare_name:
                                found_results.append(str(item))
                                if max_result and len(found_results) >= max_result:
                                    return found_results
                    except (PermissionError, OSError):
                        continue
            
            deep_dirs = deque(temp_deep_dir)
        
        if not found_results:
            raise FileNotFoundError(f"No Such File: {file_name} under {root_dir}")
        
        return found_results


if __name__ == "__main__":
    # Test script
    root = "/"
    this_file = Path(__file__).name
    try:
        print(f"Searching for {this_file} in {root}...")
        print(Explorer.search_file(root, this_file, max_result=9))
    except Exception as e:
        print(e)