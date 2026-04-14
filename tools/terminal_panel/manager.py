from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Literal

PanelMode = Literal["read_only", "write_only", "full"]

_CONTROL_CONNECT_TIMEOUT = 10.0
_CONTROL_WAIT_TIMEOUT = 3.0


def _ensure_desktop_platform() -> None:
    """
        Ensure the current platform is a desktop OS.
        raise: NotImplementedError: if the platform is mobile (android/ios)
    """
    if sys.platform in {"android", "ios"}:
        raise NotImplementedError("terminal panels are not supported on mobile platforms")


def _normalize_command(command: Iterable[str]) -> tuple[str, ...]:
    """
        Normalize the input command into a tuple of strings.
        param: command: the command arguments to normalize
        return: a tuple of string arguments
        raise: TypeError: if command is a plain string or bytes
        raise: ValueError: if command is empty
    """
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an iterable of arguments, not a plain string")

    command_list = tuple(str(part) for part in command)
    if not command_list:
        raise ValueError("command must not be empty")
    return command_list


def _normalize_mode(mode: PanelMode) -> PanelMode:
    """
        Validate and return the panel mode.
        param: mode: the mode string to validate
        return: the validated PanelMode
        raise: ValueError: if the mode is invalid
    """
    if mode not in {"read_only", "write_only", "full"}:
        raise ValueError("mode must be one of: 'read_only', 'write_only', 'full'")
    return mode


def _merge_env(overrides: dict[str, str] | None) -> dict[str, str]:
    """
        Merge environment variable overrides with the current environment.
        param: overrides: a dictionary of environment variables to override
        return: a new dictionary containing the merged environment
    """
    env = os.environ.copy()
    if overrides:
        for key, value in overrides.items():
            env[str(key)] = str(value)
    return env


def _encode_payload(payload: dict[str, Any]) -> str:
    """
        Encode a dictionary payload into a base64 string.
        param: payload: the dictionary to encode
        return: a base64 encoded URL-safe string
    """
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_payload(encoded_payload: str) -> dict[str, Any]:
    """
        Decode a base64 encoded payload back into a dictionary.
        param: encoded_payload: the base64 string to decode
        return: the decoded dictionary
    """
    raw = base64.urlsafe_b64decode(encoded_payload.encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _json_send_line(sock: socket.socket, payload: dict[str, Any]) -> None:
    """
        Send a JSON payload followed by a newline over a socket.
        param: sock: the socket to send data through
        param: payload: the dictionary payload to send
    """
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    sock.sendall(data)


def _recv_json_line(sock: socket.socket, timeout: float) -> dict[str, Any]:
    """
        Receive a single line of JSON from a socket.
        param: sock: the socket to receive from
        param: timeout: the timeout for the receive operation
        return: the decoded JSON dictionary
        raise: TimeoutError: if the line is not received within the timeout
    """
    sock.settimeout(timeout)
    buffer = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk or chunk == b"\n":
            break
        buffer.extend(chunk)
    if not buffer:
        raise TimeoutError("panel bootstrap did not become ready in time")
    return json.loads(buffer.decode("utf-8"))


def _shell_quote(text: str) -> str:
    """
        Quote a string for use in a shell command.
        param: text: the string to quote
        return: the shell-quoted string
    """
    return shlex.quote(text)


def _escape_applescript(text: str) -> str:
    """
        Escape a string for use within an AppleScript string literal.
        param: text: the string to escape
        return: the escaped string
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _module_path() -> str:
    """
        Get the absolute path of the current module.
        return: the absolute file path as a string
    """
    return os.fspath(Path(__file__).resolve())


def _python_executable() -> str:
    """
        Get the path to the current Python executable.
        return: the Python executable path
    """
    return sys.executable


def _bootstrap_script_path() -> Path:
    """
        Generate a unique temporary path for the bootstrap script.
        return: a Path object pointing to the temporary script
    """
    suffix = ".command" if sys.platform == "darwin" else ".sh"
    return Path(tempfile.gettempdir()) / f"pye_panel_{uuid.uuid4().hex}{suffix}"


def _create_bootstrap_script(
    payload_b64: str,
    *,
    cwd: str | os.PathLike[str] | None,
) -> Path:
    """
        Create a shell bootstrap script to launch the panel.
        param: payload_b64: the base64 encoded payload for the panel
        param: cwd: the working directory for the script
        return: the Path to the created executable script
    """
    script_path = _bootstrap_script_path()
    lines = [
        "#!/bin/sh",
        "set -eu",
        "trap 'rm -f \"$0\"' EXIT HUP INT TERM",
    ]
    if cwd is not None:
        lines.append(f"cd -- {_shell_quote(os.fspath(cwd))}")
    lines.extend(
        [
            f"export PYE_PANEL_PAYLOAD={_shell_quote(payload_b64)}",
            f"exec {_shell_quote(_python_executable())} -u {_shell_quote(_module_path())} --panel-bootstrap",
        ]
    )
    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def _launch_terminal_launcher(
    launcher_command: list[str],
    *,
    cwd: str | os.PathLike[str] | None,
    env: dict[str, str],
) -> subprocess.Popen[str]:
    """
        Launch a terminal emulator using a specific command.
        param: launcher_command: the command to execute
        param: cwd: the working directory for the process
        param: env: the environment variables for the process
        return: the Popen instance for the terminal process
    """
    return subprocess.Popen(
        launcher_command,
        stdin=None,
        stdout=None,
        stderr=None,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
        start_new_session=True,
    )


def _terminal_launcher_candidates(script_path: Path) -> list[tuple[str, list[str]]]:
    """
        Get a list of potential terminal emulator commands for the current platform.
        param: script_path: the path to the script to execute in the terminal
        return: a list of tuples containing launcher names and their commands
    """
    script_text = os.fspath(script_path)
    wrapped = _shell_quote(script_text)

    if sys.platform == "darwin":
        apple_script = f'tell application "Terminal" to do script "{_escape_applescript(wrapped)}"'
        return [
            ("osascript_terminal", ["osascript", "-e", apple_script]),
            ("open_terminal", ["open", "-a", "Terminal.app", script_text]),
        ]

    return [
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", "sh", "-lc", wrapped]),
        ("gnome-terminal", ["gnome-terminal", "--", "sh", "-lc", wrapped]),
        ("mate-terminal", ["mate-terminal", "--", "sh", "-lc", wrapped]),
        ("xfce4-terminal", ["xfce4-terminal", "--execute", "sh", "-lc", wrapped]),
        ("xterm", ["xterm", "-e", "sh", "-lc", wrapped]),
        ("konsole", ["konsole", "-e", "sh", "-lc", wrapped]),
        ("lxterminal", ["lxterminal", "-e", "sh", "-lc", wrapped]),
        ("alacritty", ["alacritty", "-e", "sh", "-lc", wrapped]),
        ("kitty", ["kitty", "sh", "-lc", wrapped]),
        ("wezterm", ["wezterm", "start", "--", "sh", "-lc", wrapped]),
    ]


class DisplayInterface:
    """Own the full lifecycle of a launched terminal panel."""

    def __init__(
        self,
        command: Iterable[str],
        *,
        mode: PanelMode = "full",
        allow_user_close: bool = False,
        cwd: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> None:
        """
            Initialize the DisplayInterface and open the panel.
            param: command: the command to run inside the panel
            param: mode: the operation mode ('read_only', 'write_only', 'full')
            param: allow_user_close: whether unexpected closure is allowed
            param: cwd: the working directory
            param: env: environment variable overrides
            param: title: the title of the terminal window
        """
        _ensure_desktop_platform()
        self.command = _normalize_command(command)
        self.mode = _normalize_mode(mode)
        self.allow_user_close = bool(allow_user_close)
        self.cwd = cwd
        self.env = dict(env) if env is not None else None
        self.title = title or "PyE_P2P panel"

        self._is_open = False
        self._process: subprocess.Popen[str] | None = None
        self._control_socket: socket.socket | None = None
        self._control_server: socket.socket | None = None
        self._bootstrap_script: Path | None = None
        self._pending_display_text: list[str] = []
        self._started_at = time.time()
        self._session_index = 0

        self.open()

    @property
    def is_open(self) -> bool:
        """
            Check if the panel is currently open.
            return: True if open, False otherwise
        """
        return self._is_open

    @property
    def pid(self) -> int | None:
        """
            Get the process ID of the panel.
            return: the PID as an integer, or None if not running
        """
        if self._process is None:
            return None
        return self._process.pid

    def poll(self) -> int | None:
        """
            Check if the panel process has terminated.
            return: the exit code if terminated, None otherwise
        """
        if self._process is None:
            return None
        return_code = self._process.poll()
        if return_code is None:
            return None
        return self._finalize_exit(return_code)

    def wait(self, timeout: float | None = None) -> int | None:
        """
            Wait for the panel process to terminate.
            param: timeout: maximum time to wait in seconds
            return: the exit code of the process
        """
        if self._process is None:
            return None
        return_code = self._process.wait(timeout=timeout)
        return self._finalize_exit(return_code)

    def terminate(self):
        """
            Terminate the panel process.
        """
        if self._process is not None:
            self._process.terminate()

    def kill(self):
        """
            Kill the panel process immediately.
        """
        if self._process is not None:
            self._process.kill()

    def display_text(self, text: str):
        """
            Queue or send text to be displayed in the panel.
            param: text: the string to display
        """
        message = str(text)
        if not message:
            return
        self._pending_display_text.append(message)
        if self.is_open:
            self._flush_display_text()

    def set_open(self, open_panel: bool):
        """
            Set the desired state of the panel.
            param: open_panel: whether to open or close the panel
        """
        if open_panel:
            if self.is_open:
                return
            self.open()
            return

        if not self.is_open:
            return
        self.close()

    def open(self):
        """
            Open the terminal panel and start the session.
        """
        if self.is_open:
            return

        self._cleanup_session(keep_pending=True)
        self._start_session()
        self._is_open = True
        self._flush_display_text()

    def close(self):
        """
            Close the terminal panel and cleanup the session.
        """
        if not self.is_open:
            self._cleanup_session(keep_pending=True)
            return

        try:
            if self._control_socket is not None:
                _json_send_line(self._control_socket, {"action": "close"})
        except OSError:
            pass

        if self._process is not None:
            try:
                self._process.wait(timeout=_CONTROL_WAIT_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                try:
                    self._process.wait(timeout=_CONTROL_WAIT_TIMEOUT)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=_CONTROL_WAIT_TIMEOUT)
        self._cleanup_session(keep_pending=True)

    def _cleanup_session(self, *, keep_pending: bool):
        """
            Private method to clean up session resources.
            param: keep_pending: whether to preserve pending display text
        """
        if self._control_socket is not None:
            try:
                self._control_socket.close()
            finally:
                self._control_socket = None

        if self._control_server is not None:
            try:
                self._control_server.close()
            finally:
                self._control_server = None

        self._process = None
        self._is_open = False

        if self._bootstrap_script is not None:
            try:
                self._bootstrap_script.unlink(missing_ok=True)
            except OSError:
                pass
            self._bootstrap_script = None

        if not keep_pending:
            self._pending_display_text.clear()

    def _start_session(self):
        """
            Private method to initialize and launch a new panel session.
            raise: TimeoutError: if the panel fails to connect back
            raise: RuntimeError: if the readiness message is invalid
        """
        self._session_index += 1
        control_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        control_server.bind(("127.0.0.1", 0))
        control_server.listen(1)
        control_server.settimeout(_CONTROL_CONNECT_TIMEOUT)
        self._control_server = control_server

        host, port = control_server.getsockname()
        payload = {
            "command": list(self.command),
            "mode": self.mode,
            "cwd": os.fspath(self.cwd) if self.cwd is not None else None,
            "env": self.env,
            "title": self.title,
            "control_host": host,
            "control_port": port,
        }
        payload_b64 = _encode_payload(payload)

        launch_env = _merge_env(self.env)
        launch_env["PYE_PANEL_PAYLOAD"] = payload_b64
        launch_env["PYTHONUNBUFFERED"] = "1"

        if sys.platform.startswith("win"):
            self._launch_windows_session(launch_env)
        else:
            self._launch_posix_session(launch_env, payload_b64)

        try:
            control_socket, _ = control_server.accept()
        except (socket.timeout, TimeoutError) as exc:
            self._terminate_launcher()
            self._cleanup_session(keep_pending=True)
            raise TimeoutError("panel bootstrap did not connect back in time") from exc

        control_socket.settimeout(None)
        self._control_socket = control_socket

        try:
            ready_message = _recv_json_line(control_socket, _CONTROL_CONNECT_TIMEOUT)
        except (socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            self._terminate_launcher()
            self._cleanup_session(keep_pending=True)
            raise RuntimeError("panel bootstrap returned an invalid readiness message") from exc

        if ready_message.get("action") != "ready":
            self._terminate_launcher()
            self._cleanup_session(keep_pending=True)
            raise RuntimeError("panel bootstrap returned an invalid readiness message")

        control_socket.settimeout(None)

    def _launch_windows_session(self, launch_env: dict[str, str]):
        """
            Private method to launch the panel on Windows.
            param: launch_env: the environment to use for the process
        """
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        bootstrap_command = subprocess.list2cmdline(
            [
                sys.executable,
                "-u",
                _module_path(),
                "--panel-bootstrap",
            ]
        )

        host_command = [comspec, "/d", "/k", bootstrap_command]

        process = subprocess.Popen(
            host_command,
            stdin=None,
            stdout=None,
            stderr=None,
            cwd=self.cwd,
            env=launch_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        self._process = process

    def _launch_posix_session(self, launch_env: dict[str, str], payload_b64: str):
        """
            Private method to launch the panel on POSIX systems.
            param: launch_env: the environment variables
            param: payload_b64: the base64 payload
        """
        try:
            self._bootstrap_script = _create_bootstrap_script(payload_b64, cwd=self.cwd)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    _module_path(),
                    "--panel-bootstrap",
                ],
                stdin=None,
                stdout=None,
                stderr=None,
                cwd=self.cwd,
                env=launch_env,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
            )
            self._process = process
            return
        except Exception:
            if self._bootstrap_script is None:
                raise RuntimeError("unable to create panel bootstrap script")

        candidates = _terminal_launcher_candidates(self._bootstrap_script)
        for launcher_name, launcher_command in candidates:
            if shutil.which(launcher_command[0]) is None:
                continue
            try:
                self._process = _launch_terminal_launcher(
                    launcher_command,
                    cwd=self.cwd,
                    env=launch_env,
                )
                self._launcher_name = launcher_name
                return
            except OSError:
                continue

        process = subprocess.Popen(
            [os.fspath(self._bootstrap_script)],
            stdin=None,
            stdout=None,
            stderr=None,
            cwd=self.cwd,
            env=launch_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
        self._process = process

    def _terminate_launcher(self):
        """
            Private method to terminate the launcher process.
        """
        if self._process is None:
            return
        try:
            self._process.terminate()
        except OSError:
            pass

    def _finalize_exit(self, return_code: int) -> int:
        """
            Private method to handle the finalization of the panel exit.
            param: return_code: the exit code of the process
            return: the return code if successful or allowed
            raise: RuntimeError: if the exit code is non-zero and not allowed
        """
        self._cleanup_session(keep_pending=True)
        if return_code == 0 or self.allow_user_close:
            return return_code
        raise RuntimeError(f"terminal panel exited unexpectedly with code {return_code}")

    def _flush_display_text(self):
        """
            Private method to send all pending text to the panel.
            raise: RuntimeError: if the control channel becomes unavailable
        """
        if not self.is_open or self._control_socket is None:
            return

        while self._pending_display_text:
            next_text = self._pending_display_text[0]
            try:
                _json_send_line(self._control_socket, {"action": "display_text", "text": next_text})
            except OSError as exc:
                if self.allow_user_close:
                    self._cleanup_session(keep_pending=True)
                    return
                raise RuntimeError("panel control channel is unavailable") from exc
            self._pending_display_text.pop(0)


def managerPanel(
    panel: DisplayInterface,
    DISPLAY_TEXT: str | None = None,
    *,
    open_panel: bool | None = None,
    wait: bool = False,
    timeout: float | None = None,
) -> int | None:
    """
        Drive a DisplayInterface session.
        param: panel: the DisplayInterface instance to manage
        param: DISPLAY_TEXT: optional text to display
        param: open_panel: whether to set the panel state to open/closed
        param: wait: whether to wait for the panel to finish
        param: timeout: timeout for waiting
        return: the exit code or poll result
    """
    _ensure_desktop_platform()

    if DISPLAY_TEXT is not None:
        panel.display_text(DISPLAY_TEXT)

    if open_panel is not None:
        panel.set_open(open_panel)

    if wait:
        return panel.wait(timeout=timeout)

    return panel.poll()


def _panel_worker_main() -> int:
    """
        The main entry point for the panel worker process.
        return: the exit code of the child process
        raise: RuntimeError: if payload is missing or invalid
    """
    payload_b64 = os.environ.get("PYE_PANEL_PAYLOAD")
    if not payload_b64:
        raise RuntimeError("missing panel payload")

    payload = _decode_payload(payload_b64)
    command = tuple(str(part) for part in payload["command"])
    mode = _normalize_mode(payload["mode"])
    cwd = payload.get("cwd")
    env_overrides = payload.get("env") or {}
    title = payload.get("title")
    control_host = str(payload["control_host"])
    control_port = int(payload["control_port"])

    if title:
        if sys.platform.startswith("win"):
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleTitleW(str(title))
            except Exception:
                pass
        else:
            sys.stdout.write(f"\033]0;{title}\a")
            sys.stdout.flush()

    control_socket = socket.create_connection((control_host, control_port), timeout=_CONTROL_CONNECT_TIMEOUT)
    _json_send_line(control_socket, {"action": "ready"})
    control_socket.settimeout(None)

    child_env = os.environ.copy()
    for key, value in env_overrides.items():
        child_env[str(key)] = str(value)

    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=child_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=False,
    )

    stop_event = threading.Event()

    def _write_stdout(text: str):
        if text:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _write_stderr(text: str):
        if text:
            sys.stderr.write(text)
            sys.stderr.flush()

    def _drain_stream(stream: Any):
        try:
            for chunk in iter(stream.readline, ""):
                if stop_event.is_set():
                    break
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _relay_stream(stream: Any, writer: Any):
        try:
            for chunk in iter(stream.readline, ""):
                if stop_event.is_set():
                    break
                writer(chunk)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _stdin_forwarder():
        if child.stdin is None:
            return
        try:
            for line in iter(sys.stdin.readline, ""):
                if stop_event.is_set():
                    break
                if mode == "read_only":
                    continue
                child.stdin.write(line)
                child.stdin.flush()
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    def _control_loop():
        reader = control_socket.makefile("r", encoding="utf-8", newline="\n")
        try:
            for line in iter(reader.readline, ""):
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if message.get("action") == "display_text":
                    _write_stdout(str(message.get("text", "")))
                elif message.get("action") == "close":
                    stop_event.set()
                    if child.poll() is None:
                        child.terminate()
                    break
        finally:
            try:
                reader.close()
            except OSError:
                pass

    threads: list[threading.Thread] = []
    threads.append(threading.Thread(target=_control_loop, daemon=True))
    threads.append(threading.Thread(target=_stdin_forwarder, daemon=True))

    if mode in {"full", "read_only"}:
        threads.append(threading.Thread(target=_relay_stream, args=(child.stdout, _write_stdout), daemon=True))
        threads.append(threading.Thread(target=_relay_stream, args=(child.stderr, _write_stderr), daemon=True))
    else:
        threads.append(threading.Thread(target=_drain_stream, args=(child.stdout,), daemon=True))
        threads.append(threading.Thread(target=_drain_stream, args=(child.stderr,), daemon=True))

    for thread in threads:
        thread.start()

    try:
        return_code = child.wait()
    finally:
        stop_event.set()
        try:
            control_socket.close()
        except OSError:
            pass

    return int(return_code)


def _smoke_test():
    """
        Run a diagnostic smoke test to verify panel functionality.
        raise: RuntimeError: if the test behavior does not match expectations
    """
    child_code = (
        "import sys\n"
        r"print('panel ready\n', flush=True)"
        "\nsys.exit(7)\n"
    )

    strict_panel = DisplayInterface(
        [sys.executable, "-u", "-c", child_code],
        mode="read_only",
        allow_user_close=False,
    )
    try:
        managerPanel(strict_panel, DISPLAY_TEXT="hello from DISPLAY_TEXT")
        try:
            strict_panel.wait(timeout=10)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("strict mode should raise when the panel exits unexpectedly")
    finally:
        strict_panel.close()

    permissive_panel = DisplayInterface(
        [sys.executable, "-u", "-c", child_code],
        mode="read_only",
        allow_user_close=True,
    )
    try:
        managerPanel(permissive_panel, DISPLAY_TEXT="hello from DISPLAY_TEXT")
        return_code = permissive_panel.wait(timeout=10)
        if return_code != 7:
            raise RuntimeError(f"smoke test child exited with code {return_code}")
    finally:
        permissive_panel.close()


if __name__ == "__main__":
    if "--panel-bootstrap" in sys.argv:
        raise SystemExit(_panel_worker_main())

    if "--smoke-test" in sys.argv or len(sys.argv) == 1:
        _smoke_test()


__all__ = ["DisplayInterface", "managerPanel"]
