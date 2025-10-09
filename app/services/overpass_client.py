"""Utility helpers to query Overpass API with mirror rotation and retries."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Tuple

import requests

OVERPASS_ENDPOINTS: list[str] = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.belgium.be/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

_HEADERS = {
    "User-Agent": "MFYLocalApp/1.0 (+contact@yourdomain)",
    "Accept": "application/json",
}

_TIMEOUT = 25
_STATUS_TIMEOUT = 3
_MAX_RETRIES = 2  # retries per mirror after the first attempt
_BACKOFF_BASES = (0.6, 1.2)


def _has_available_slot(endpoint: str) -> bool:
    status_url = endpoint.replace("interpreter", "status")
    try:
        response = requests.get(status_url, headers=_HEADERS, timeout=_STATUS_TIMEOUT)
    except requests.RequestException:
        return True
    if not response.ok:
        return True
    body = response.text.lower()
    if "slots available" in body and "slots available: 0" in body:
        return False
    return True


def _sleep_with_jitter(base: float) -> None:
    jitter = base * random.uniform(0.75, 1.25)
    time.sleep(jitter)


def query_overpass(query: str, label: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Execute an Overpass query using rotating mirrors and retries.

    Returns a tuple ``(elements, debug)`` where ``elements`` is the list of
    Overpass elements (or an empty list on failure) and ``debug`` contains
    metadata about the request.
    """

    last_debug: Dict[str, Any] = {
        "label": label,
        "status": "error",
        "error": "no_endpoint_available",
        "mirror": None,
        "attempts": 0,
    }

    for endpoint in OVERPASS_ENDPOINTS:
        if not _has_available_slot(endpoint):
            continue
        attempts = 0
        for retry in range(_MAX_RETRIES + 1):
            attempts += 1
            start = time.perf_counter()
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=_HEADERS,
                    timeout=_TIMEOUT,
                )
            except requests.Timeout:
                duration_ms = int((time.perf_counter() - start) * 1000)
                last_debug = {
                    "label": label,
                    "status": "timeout",
                    "mirror": endpoint,
                    "attempts": attempts,
                    "duration_ms": duration_ms,
                }
                break
            except requests.RequestException as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                last_debug = {
                    "label": label,
                    "status": "error",
                    "error": str(exc),
                    "mirror": endpoint,
                    "attempts": attempts,
                    "duration_ms": duration_ms,
                }
                if retry < _MAX_RETRIES:
                    _sleep_with_jitter(_BACKOFF_BASES[min(retry, len(_BACKOFF_BASES) - 1)])
                    continue
                break

            duration_ms = int((time.perf_counter() - start) * 1000)
            status_code = response.status_code
            base_debug = {
                "label": label,
                "mirror": endpoint,
                "attempts": attempts,
                "duration_ms": duration_ms,
                "status_code": status_code,
            }

            if status_code == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    last_debug = {
                        **base_debug,
                        "status": "error",
                        "error": f"invalid_json: {exc}",
                    }
                    break
                elements = payload.get("elements", [])
                debug = {
                    **base_debug,
                    "status": "ok",
                    "items": len(elements),
                }
                return elements, debug

            if status_code == 504:
                last_debug = {
                    **base_debug,
                    "status": "timeout",
                    "error": "http_504",
                }
                break

            if status_code == 429 or 500 <= status_code < 600:
                last_debug = {
                    **base_debug,
                    "status": "error",
                    "error": f"http_{status_code}",
                }
                if retry < _MAX_RETRIES:
                    _sleep_with_jitter(_BACKOFF_BASES[min(retry, len(_BACKOFF_BASES) - 1)])
                    continue
                break

            last_debug = {
                **base_debug,
                "status": "error",
                "error": f"http_{status_code}",
            }
            break

        if last_debug.get("status") == "ok":
            return [], last_debug
        if last_debug.get("status") == "timeout":
            continue
    return [], last_debug

