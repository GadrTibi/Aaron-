"""Disk-based cache helpers for Wikimedia services."""
from __future__ import annotations

import json
import time
from hashlib import sha1
from pathlib import Path
from typing import Any

from config import wiki_settings


def get_cache_path(key: str) -> Path:
    """Return the cache path associated to ``key``."""
    digest = sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()
    cache_dir = Path(wiki_settings.CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{digest}.json"


def read_cache_json(key: str, max_age_sec: int) -> dict[str, Any] | None:
    """Read a JSON payload from cache if it exists and is fresh."""
    path = get_cache_path(key)
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > max_age_sec:
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def write_cache_json(key: str, data: dict[str, Any]) -> None:
    """Write JSON data to the cache."""
    path = get_cache_path(key)
    try:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError as exc:
        raise RuntimeError(f"Unable to write cache file {path!s}: {exc}") from exc


__all__ = ["get_cache_path", "read_cache_json", "write_cache_json"]
