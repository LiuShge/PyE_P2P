"""
Public IP acquisition module.
"""

import urllib.request, urllib.error
import json
import ipaddress
from pathlib import Path
from collections import Counter
import threading

from typing import Any, List
from collections.abc import Iterable

BASE_DIR = Path(__file__).resolve().parent

class InternetError(Exception):
    """Raised when public IP acquisition fails."""
    pass

def js_decode(unjson_context: str|bytes|dict, auto: bool = True):
    """
        Decode a JSON payload into a Python object.
        param: unjson_context: a JSON string, raw bytes, or an already-decoded dict
        param: auto: if True, bytes are decoded to text and dict inputs are returned as is
        return: any Python object produced by json.loads, or the original dict
        raise: ValueError: if bytes cannot be converted to text
        raise: TypeError: if the payload cannot be parsed as JSON
    """
    def safety_convert(context: Any) -> Any:
        try:
            return json.loads(context)
        except json.JSONDecodeError as e:
            raise TypeError("Can't convert the arg unjson_context to dict_type") from e
    
    if auto:
        if isinstance(unjson_context, dict):
            return unjson_context
        try:
            unjson_context = unjson_context.decode() if isinstance(unjson_context, bytes) else unjson_context # type: ignore
        except Exception as e:
            raise ValueError("Can't convert the arg unjson_context to str_type.") from e
    
    json_context = safety_convert(unjson_context)
    
    return json_context

def url_of_external_ip_provider()->List[str]:
    """
        Load public IP provider URLs from provider.json.
        return: a list of provider URLs stored in the local configuration file
        raise: TypeError: if the file is invalid JSON or contains non-string URLs
    """
    try:
        with open(BASE_DIR / "provider.json", encoding='utf-8', mode='r') as f:
            urls = js_decode(f.read())
        if not isinstance(urls, dict):
            raise TypeError("Disallowed file format: provider.json file may have been maliciously tampered with")
        if not all(isinstance(url, str) for url in urls.values()):
            raise TypeError("Disallowed file format: provider.json must contain string URLs")
    except json.JSONDecodeError as e:
        raise TypeError("Unsupported file format: the provider.json file may be corrupted") from e
    
    return list(urls.values())

def _decode_ip_payload(payload: bytes | str) -> str:
    """
        Normalize a provider response into a plain IP string.
        param: payload: raw response bytes or text returned by a provider
        return: a stripped string containing the IP candidate
    """
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace").strip()
    else:
        text = payload.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(data, dict) and data:
        return str(next(iter(data.values()))).strip()

    return str(data).strip()

def _is_valid_ip(candidate: str) -> bool:
    """
        Check if the candidate string is a valid IP address.
        param: candidate: the IP string to validate
        return: True when candidate is syntactically valid, False otherwise
    """
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        return False

def get_ip(urls_of_providers: Iterable[str],
           times_of_retries: int = 3,
           timeout: int = 4) -> str:
    """
        Fetch the most likely public IP from multiple providers in parallel.
        param: urls_of_providers: a sequence of provider URLs
        param: times_of_retries: retry count for each provider before failing
        param: timeout: socket timeout for the request
        return: the most common IP candidate reported by the providers
        raise: InternetError: if provider links are invalid or network fails
        raise: RuntimeError: if no provider returns usable IP data
    """
    
    urls_of_providers = list(urls_of_providers)

    ips = []
    errors = []
    lock = threading.Lock()

    def fetch_ip(url: str) -> None:
        passed: bool = False
        retry_times: int = 0
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "PyE_P2P/0.1 (+https://github.com/)"},
        )
        while not passed:
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    data = _decode_ip_payload(response.read())
                if not data or not _is_valid_ip(data):
                    raise ValueError("Empty IP response")
                with lock:
                    ips.append(data)
                passed = True
            except urllib.error.URLError:
                with lock:
                    errors.append(InternetError("The link in provider.json is invalid."))
                return
            except Exception as e:
                retry_times += 1
                if retry_times < times_of_retries:
                    continue
                with lock:
                    errors.append(InternetError("Failed to retrieve, please check your network"))
                return

    threads = [threading.Thread(target=fetch_ip, args=(url,), daemon=True) for url in urls_of_providers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if errors and not ips:
        raise errors[0]
    
    if ips:
        return Counter(ips).most_common(1)[0][0]
    
    base_err = InternetError("All attempts to obtain the IP failed.")
    raise RuntimeError("No available network IP: failed to obtain") from base_err


if __name__ == "__main__":
    import time
    time_now = time.time()
    print(get_ip(url_of_external_ip_provider()))
    time_used = time.time() - time_now
    print("Time used "+str(time_used))