from __future__ import annotations

import io
import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock

from tools.terminal_panel import manager


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False
        self.timeout = None

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True

    def settimeout(self, timeout):
        self.timeout = timeout

    def makefile(self, *args, **kwargs):
        return io.StringIO("")


class FakeProcess:
    def __init__(self, return_code: int = 0) -> None:
        self.return_code = return_code
        self.terminated = False
        self.killed = False
        self.wait_calls = 0
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")

    def poll(self):
        return self.return_code

    def wait(self, timeout=None):
        self.wait_calls += 1
        return self.return_code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TerminalPanelTests(unittest.TestCase):
    def test_helpers_roundtrip_and_validation(self) -> None:
        self.assertEqual(manager._normalize_command(["python", "-V"]), ("python", "-V"))
        self.assertEqual(manager._normalize_mode("full"), "full")
        self.assertEqual(manager._merge_env({"X": "1"})["X"], "1")

        payload = {"command": ["echo", "hi"], "mode": "full"}
        encoded = manager._encode_payload(payload)
        self.assertEqual(manager._decode_payload(encoded), payload)

        with self.assertRaises(TypeError):
            manager._normalize_command("echo hi")
        with self.assertRaises(ValueError):
            manager._normalize_mode("invalid")

    def test_launcher_candidates_by_platform(self) -> None:
        with mock.patch.object(manager.sys, "platform", "darwin"):
            candidates = manager._terminal_launcher_candidates(manager.Path("/tmp/bootstrap.sh"))
            self.assertEqual(candidates[0][0], "osascript_terminal")

        with mock.patch.object(manager.sys, "platform", "linux"):
            candidates = manager._terminal_launcher_candidates(manager.Path("/tmp/bootstrap.sh"))
            self.assertTrue(any(name == "xterm" for name, _ in candidates))

    def test_manager_panel_delegates(self) -> None:
        panel = mock.Mock()
        panel.display_text.return_value = None
        panel.set_open.return_value = None
        panel.poll.return_value = 0

        self.assertEqual(manager.managerPanel(panel, DISPLAY_TEXT="hi", open_panel=True), 0)
        panel.display_text.assert_called_once_with("hi")
        panel.set_open.assert_called_once_with(True)
        panel.poll.assert_called_once()

    def test_flush_display_text(self) -> None:
        panel = manager.DisplayInterface.__new__(manager.DisplayInterface)
        panel.allow_user_close = False
        panel._pending_display_text = ["hello"]
        panel._control_socket = FakeSocket()
        panel._is_open = True

        manager.DisplayInterface._flush_display_text(panel)

        self.assertEqual(panel._pending_display_text, [])
        sent_payload = json.loads(panel._control_socket.sent[0].decode("utf-8"))
        self.assertEqual(sent_payload["action"], "display_text")
        self.assertEqual(sent_payload["text"], "hello")

    def test_posix_bootstrap_missing_raises(self) -> None:
        panel = manager.DisplayInterface.__new__(manager.DisplayInterface)
        panel.cwd = None
        panel._bootstrap_script = None
        panel._process = None

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(manager, "_create_bootstrap_script", side_effect=RuntimeError("boom")))
            stack.enter_context(mock.patch.object(manager.sys, "platform", "linux"))
            with self.assertRaises(RuntimeError):
                manager.DisplayInterface._launch_posix_session(panel, {"X": "1"}, "payload")


if __name__ == "__main__":
    unittest.main()
