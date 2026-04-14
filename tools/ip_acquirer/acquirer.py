"""
Public IP acquisition utilities.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import threading
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, Iterable


BASE_DIR = Path(__file__).resolve().parent
_CONFIG_LOCK = threading.Lock()
_CACHE_RATIO = 0.6
_CACHE_SCHEMA_VERSION = 1


class PublicIPError(Exception):
    """Base class for public IP lookup failures."""


class ProviderConfigError(PublicIPError):
    """Raised when provider configuration is missing or invalid."""


class ProviderRequestError(PublicIPError):
    """Raised when an individual provider cannot be queried."""

    def __init__(self, url: str, message: str, *, cause: Exception | None = None) -> None:
        self.url = url
        self.message = message
        self.cause = cause
        super().__init__(f"{url}: {message}")


class PublicIPResolutionError(PublicIPError):
    """Raised when no provider returns a valid public IP."""

    def __init__(self, message: str, *, errors: list[ProviderRequestError] | None = None) -> None:
        self.errors = tuple(errors or [])
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    """Diagnostic information for one provider request."""

    url: str
    attempts: int
    ip: str | None
    elapsed_seconds: float
    error: str | None


@dataclass(frozen=True, slots=True)
class PublicIPResult:
    """Structured result of a successful IP lookup."""

    ip: str
    provider_urls: tuple[str, ...]
    candidates: tuple[str, ...]
    attempts: tuple[ProviderAttempt, ...]
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """Provider configuration and cache metadata."""

    providers: tuple[tuple[str, str], ...]
    provider_hash: str
    fastest_urls: tuple[str, ...]
    schema_version: int

    def as_url_list(self) -> list[str]:
        return [url for _, url in self.providers]


def decode_json_payload(payload: str | bytes | dict[str, Any], *, auto: bool = True) -> Any:
    """
    Decode a JSON payload into a Python object.
    """
    if isinstance(payload, dict):
        if auto:
            return payload
        raise TypeError("payload is not valid JSON")

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")

    try:
        return json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise TypeError("payload is not valid JSON") from exc


def _normalize_provider_entries(raw_providers: Any) -> list[tuple[str, str]]:
    if not isinstance(raw_providers, dict) or not raw_providers:
        raise ProviderConfigError("provider.json must contain a non-empty JSON object")

    normalized: list[tuple[str, str]] = []
    for key, value in raw_providers.items():
        provider_name = str(key).strip()
        provider_url = str(value).strip()
        if provider_name and provider_url:
            normalized.append((provider_name, provider_url))

    if not normalized:
        raise ProviderConfigError("provider.json does not contain any usable provider URL")

    return normalized


def _compute_provider_hash(provider_entries: list[tuple[str, str]]) -> str:
    payload = json.dumps(provider_entries, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fastest_provider_count(total: int) -> int:
    return max(1, -(-total * 60 // 100))


def _load_provider_document() -> dict[str, Any]:
    provider_path = BASE_DIR / "provider.json"
    try:
        document = decode_json_payload(provider_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProviderConfigError(f"missing provider file: {provider_path}") from exc
    except OSError as exc:
        raise ProviderConfigError(f"unable to read provider file: {provider_path}") from exc
    except TypeError as exc:
        raise ProviderConfigError(f"invalid JSON in provider file: {provider_path}") from exc

    if not isinstance(document, dict):
        raise ProviderConfigError("provider.json must contain a JSON object")
    return document


def _extract_provider_config(document: dict[str, Any]) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    if "providers" in document:
        providers = document.get("providers")
        meta = document.get("meta") or {}
    else:
        providers = document
        meta = {}

    if not isinstance(meta, dict):
        meta = {}

    return _normalize_provider_entries(providers), meta


def _load_provider_config() -> ProviderConfig:
    document = _load_provider_document()
    provider_entries, meta = _extract_provider_config(document)
    return ProviderConfig(
        providers=tuple(provider_entries),
        provider_hash=_compute_provider_hash(provider_entries),
        fastest_urls=tuple(
            str(url).strip()
            for url in meta.get("fastest_urls", [])
            if str(url).strip()
        ),
        schema_version=int(meta.get("schema_version", 0) or 0),
    )


def _write_provider_config(provider_entries: list[tuple[str, str]], fastest_urls: list[str]) -> None:
    provider_path = BASE_DIR / "provider.json"
    document = {
        "meta": {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "provider_hash": _compute_provider_hash(provider_entries),
            "fastest_ratio": _CACHE_RATIO,
            "fastest_urls": fastest_urls,
        },
        "providers": {name: url for name, url in provider_entries},
    }
    provider_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )


def load_public_ip_providers() -> list[str]:
    """
    Load provider URLs from provider.json.
    """
    return _load_provider_config().as_url_list()


def _decode_ip_payload(payload: bytes | str) -> str:
    if isinstance(payload, str):
        text = payload.strip()
    else:
        text = bytes(payload).decode("utf-8", errors="replace").strip()

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(decoded, dict) and decoded:
        return str(next(iter(decoded.values()))).strip()

    return str(decoded).strip()


def _is_valid_ip(candidate: str) -> bool:
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        return False


def get_public_ip(
    urls_of_providers: Iterable[str],
    *,
    times_of_retries: int = 3,
    timeout: int = 4,
) -> PublicIPResult:
    """
    Fetch the most likely public IP from multiple providers in parallel.
    """
    provider_urls = [str(url).strip() for url in urls_of_providers if str(url).strip()]
    if not provider_urls:
        raise ProviderConfigError("at least one provider URL is required")
    if times_of_retries < 1:
        raise ValueError("times_of_retries must be at least 1")
    if timeout < 1:
        raise ValueError("timeout must be at least 1")

    ip_candidates: list[str] = []
    attempts: list[ProviderAttempt] = []
    errors: list[ProviderRequestError] = []
    lock = threading.Lock()

    def fetch_ip(url: str) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "PyE_P2P/0.1"})
        started_at = monotonic()

        for attempt_count in range(1, times_of_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    candidate = _decode_ip_payload(response.read())

                elapsed = monotonic() - started_at
                if not candidate or not _is_valid_ip(candidate):
                    raise ProviderRequestError(url, "response did not contain a valid IP address")

                with lock:
                    ip_candidates.append(candidate)
                    attempts.append(
                        ProviderAttempt(
                            url=url,
                            attempts=attempt_count,
                            ip=candidate,
                            elapsed_seconds=elapsed,
                            error=None,
                        )
                    )
                return
            except urllib.error.URLError as exc:
                elapsed = monotonic() - started_at
                wrapped = ProviderRequestError(url, "provider request failed", cause=exc)
            except ProviderRequestError as exc:
                elapsed = monotonic() - started_at
                wrapped = ProviderRequestError(url, exc.message, cause=exc.cause)
            except Exception as exc:
                elapsed = monotonic() - started_at
                wrapped = ProviderRequestError(url, str(exc) or "unexpected provider failure", cause=exc)

            with lock:
                attempts.append(
                    ProviderAttempt(
                        url=url,
                        attempts=attempt_count,
                        ip=None,
                        elapsed_seconds=elapsed,
                        error=str(wrapped),
                    )
                )

            if attempt_count >= times_of_retries:
                with lock:
                    errors.append(wrapped)
                return

    started_at = monotonic()
    threads = [threading.Thread(target=fetch_ip, args=(url,), daemon=True) for url in provider_urls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    elapsed_seconds = monotonic() - started_at

    if not ip_candidates:
        raise PublicIPResolutionError(
            "failed to obtain a valid public IP from all providers",
            errors=errors,
        )

    best_ip, _ = Counter(ip_candidates).most_common(1)[0]
    winning_urls = tuple(
        dict.fromkeys(
            attempt.url
            for attempt in attempts
            if attempt.ip == best_ip and attempt.error is None
        )
    )
    return PublicIPResult(
        ip=best_ip,
        provider_urls=winning_urls,
        candidates=tuple(ip_candidates),
        attempts=tuple(attempts),
        elapsed_seconds=elapsed_seconds,
    )


def _select_fastest_urls(attempts: Iterable[ProviderAttempt], total_provider_count: int) -> list[str]:
    fastest_target = _fastest_provider_count(total_provider_count)
    success_attempts = [attempt for attempt in attempts if attempt.ip is not None]
    ranked_urls = sorted(
        {
            attempt.url: attempt.elapsed_seconds
            for attempt in success_attempts
        }.items(),
        key=lambda item: item[1],
    )
    return [url for url, _ in ranked_urls[:fastest_target]]


def get_public_ip_from_config(
    *,
    times_of_retries: int = 3,
    timeout: int = 4,
) -> PublicIPResult:
    """
    Resolve the public IP using the configured providers.

    The first time, or whenever provider.json changes, all providers are used.
    The fastest 60% of the successful providers are cached back into provider.json.
    """
    with _CONFIG_LOCK:
        config = _load_provider_config()
        current_hash = config.provider_hash
        cached_hash = ""
        cached_urls = [url for url in config.fastest_urls if url]

        document = _load_provider_document()
        _, meta = _extract_provider_config(document)
        cached_hash = str(meta.get("provider_hash", "")).strip()

        providers_changed = cached_hash != current_hash or not cached_urls

        if providers_changed:
            result = get_public_ip(
                config.as_url_list(),
                times_of_retries=times_of_retries,
                timeout=timeout,
            )
            fastest_urls = _select_fastest_urls(result.attempts, len(config.providers))
            _write_provider_config(list(config.providers), fastest_urls)
            return result

        try:
            return get_public_ip(
                cached_urls,
                times_of_retries=times_of_retries,
                timeout=timeout,
            )
        except PublicIPResolutionError:
            result = get_public_ip(
                config.as_url_list(),
                times_of_retries=times_of_retries,
                timeout=timeout,
            )
            fastest_urls = _select_fastest_urls(result.attempts, len(config.providers))
            _write_provider_config(list(config.providers), fastest_urls)
            return result


if __name__ == "__main__":
    import time

    started = time.time()
    result = get_public_ip(load_public_ip_providers())
    print(result.ip)
    print(f"Providers: {list(result.provider_urls)}")
    print(f"Time used {time.time() - started}")
