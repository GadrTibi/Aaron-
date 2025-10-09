from __future__ import annotations

import json
import os
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "")
OPENTRIPMAP_API_KEY = os.getenv("OPENTRIPMAP_API_KEY", "")
USER_AGENT = "MFYLocalApp/1.0 (+contact@yourdomain)"
HTTP_TIMEOUT = 10
RETRIES = 2
RETRY_BASE_DELAY = 0.6
RETRY_JITTER = 0.2
CACHE_DIR = "out/cache/places"


def build_headers() -> dict[str, str]:
    """Return default HTTP headers for external services."""

    return {"User-Agent": USER_AGENT, "Accept": "application/json"}


def _ensure_cache_dir() -> Path:
    path = Path(CACHE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_cache_path(key: str) -> Path:
    """Return a cache file path derived from a key."""

    digest = sha256(key.encode("utf-8")).hexdigest()
    return _ensure_cache_dir() / f"{digest}.json"


def read_cache_json(key: str, ttl_seconds: int) -> Any | None:
    """Read a JSON payload from cache if still valid."""

    path = get_cache_path(key)
    if not path.exists():
        return None

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None

    if time.time() - mtime > ttl_seconds:
        return None

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_cache_json(key: str, data: Any) -> None:
    """Persist a JSON payload into cache."""

    path = get_cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
