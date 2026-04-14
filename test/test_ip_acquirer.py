from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import urllib.error

from tools.ip_acquirer import acquirer


class FakeResponse:
    def __init__(self, payload: str | bytes) -> None:
        self._payload = payload.encode("utf-8") if isinstance(payload, str) else payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._payload


class PublicIPTests(unittest.TestCase):
    def test_decode_json_payload(self) -> None:
        self.assertEqual(acquirer.decode_json_payload({"a": 1}), {"a": 1})
        self.assertEqual(acquirer.decode_json_payload(b'{"a": 1}'), {"a": 1})
        self.assertEqual(acquirer.decode_json_payload('{"a": 1}'), {"a": 1})
        with self.assertRaises(TypeError):
            acquirer.decode_json_payload("not json")

    def test_get_public_ip_majority_vote(self) -> None:
        provider_urls = ["https://one.example/ip", "https://two.example/ip", "https://three.example/ip"]
        payloads = {
            "https://one.example/ip": "203.0.113.9",
            "https://two.example/ip": '{"ip": "203.0.113.9"}',
            "https://three.example/ip": "198.51.100.7",
        }

        def fake_urlopen(request, timeout=0):
            return FakeResponse(payloads[request.full_url])

        with mock.patch.object(acquirer.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = acquirer.get_public_ip(provider_urls, times_of_retries=1, timeout=1)

        self.assertEqual(result.ip, "203.0.113.9")
        self.assertEqual(set(result.provider_urls), {"https://one.example/ip", "https://two.example/ip"})
        self.assertEqual(len(result.attempts), 3)
        self.assertEqual(sorted(result.candidates), ["198.51.100.7", "203.0.113.9", "203.0.113.9"])

    def test_get_public_ip_raises_when_all_providers_fail(self) -> None:
        def fake_urlopen(request, timeout=0):
            raise urllib.error.URLError("offline")

        with mock.patch.object(acquirer.urllib.request, "urlopen", side_effect=fake_urlopen):
            with self.assertRaises(acquirer.PublicIPResolutionError) as ctx:
                acquirer.get_public_ip(["https://one.example/ip"], times_of_retries=2, timeout=1)

        self.assertEqual(len(ctx.exception.errors), 1)
        self.assertIn("failed to obtain a valid public IP", str(ctx.exception))

    def test_config_cache_branch_uses_cached_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            provider_file = base_dir / "provider.json"
            provider_document = {
                "meta": {
                    "schema_version": 1,
                    "provider_hash": "hash-1",
                    "fastest_urls": ["https://cached.example/ip"],
                },
                "providers": {
                    "a": "https://one.example/ip",
                    "b": "https://cached.example/ip",
                },
            }
            provider_file.write_text(json.dumps(provider_document), encoding="utf-8")

            cached_result = acquirer.PublicIPResult(
                ip="203.0.113.9",
                provider_urls=("https://cached.example/ip",),
                candidates=("203.0.113.9",),
                attempts=(),
                elapsed_seconds=0.1,
            )

            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(acquirer, "BASE_DIR", base_dir))
                stack.enter_context(mock.patch.object(acquirer, "_load_provider_config", return_value=acquirer.ProviderConfig(
                    providers=(("a", "https://one.example/ip"), ("b", "https://cached.example/ip")),
                    provider_hash="hash-1",
                    fastest_urls=("https://cached.example/ip",),
                    schema_version=1,
                )))
                get_mock = stack.enter_context(mock.patch.object(acquirer, "get_public_ip", return_value=cached_result))
                write_mock = stack.enter_context(mock.patch.object(acquirer, "_write_provider_config"))

                result = acquirer.get_public_ip_from_config(times_of_retries=1, timeout=1)

            self.assertEqual(result.ip, "203.0.113.9")
            get_mock.assert_called_once_with(["https://cached.example/ip"], times_of_retries=1, timeout=1)
            write_mock.assert_not_called()

    def test_config_refresh_branch_writes_fastest_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            provider_file = base_dir / "provider.json"
            provider_document = {
                "meta": {
                    "schema_version": 1,
                    "provider_hash": "stale-hash",
                    "fastest_urls": [],
                },
                "providers": {
                    "a": "https://one.example/ip",
                    "b": "https://two.example/ip",
                    "c": "https://three.example/ip",
                },
            }
            provider_file.write_text(json.dumps(provider_document), encoding="utf-8")

            fresh_result = acquirer.PublicIPResult(
                ip="203.0.113.9",
                provider_urls=("https://two.example/ip",),
                candidates=("203.0.113.9", "203.0.113.9", "198.51.100.7"),
                attempts=(
                    acquirer.ProviderAttempt("https://one.example/ip", 1, "203.0.113.9", 0.4, None),
                    acquirer.ProviderAttempt("https://two.example/ip", 1, "203.0.113.9", 0.1, None),
                    acquirer.ProviderAttempt("https://three.example/ip", 1, "198.51.100.7", 0.2, None),
                ),
                elapsed_seconds=0.4,
            )

            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(acquirer, "BASE_DIR", base_dir))
                stack.enter_context(mock.patch.object(acquirer, "get_public_ip", return_value=fresh_result))
                write_mock = stack.enter_context(mock.patch.object(acquirer, "_write_provider_config"))

                result = acquirer.get_public_ip_from_config(times_of_retries=1, timeout=1)

            self.assertEqual(result.ip, "203.0.113.9")
            write_mock.assert_called_once()
            written_entries = write_mock.call_args.args[0]
            written_fastest = write_mock.call_args.args[1]
            self.assertEqual(len(written_entries), 3)
            self.assertEqual(written_fastest, ["https://two.example/ip", "https://three.example/ip"])


if __name__ == "__main__":
    unittest.main()
