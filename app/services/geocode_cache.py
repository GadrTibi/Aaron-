"""Persistent disk cache for geocoding results."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Iterable, Tuple


DEFAULT_CACHE_DIR = Path(os.getenv("MFY_GEOCODE_CACHE_DIR", "out/cache/geocode"))


def normalize_address(value: str) -> str:
    """Return a normalized address string used for caching and comparisons."""

    words = [part for part in (value or "").strip().split() if part]
    return " ".join(words).lower()


def cache_key(address: str) -> str:
    normalized = normalize_address(address)
    return hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()


def _cache_file(address: str, base_dir: Path | str | None = None) -> Path:
    folder = Path(base_dir) if base_dir is not None else DEFAULT_CACHE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{cache_key(address)}.json"


def _is_expired(ts: float, ttl_seconds: float) -> bool:
    try:
        return (time.time() - float(ts)) > ttl_seconds
    except Exception:
        return True


def _read_json(path: Path) -> dict:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        return json.loads(payload)
    except Exception:
        return {}


def get_cached_geocode(
    address: str,
    *,
    base_dir: Path | str | None = None,
    ttl_seconds: float | None = None,
) -> Tuple[float, float, str] | None:
    """Return cached coordinates if still valid.

    Parameters
    ----------
    address : str
        The human readable address to check.
    base_dir : Path | str | None
        Cache root directory. Defaults to ``out/cache/geocode`` or the
        ``MFY_GEOCODE_CACHE_DIR`` environment variable.
    ttl_seconds : float | None
        Custom TTL in seconds. Defaults to 30 days when omitted.
    """

    ttl = ttl_seconds if ttl_seconds is not None else float(os.getenv("MFY_GEOCODE_CACHE_TTL", 30 * 24 * 3600))
    target = _cache_file(address, base_dir)
    if not target.exists():
        return None

    payload = _read_json(target)
    ts = payload.get("ts")
    if ts is None or _is_expired(ts, ttl):
        return None

    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
    except (TypeError, ValueError):
        return None
    provider = str(payload.get("provider")) if payload.get("provider") else ""
    return lat, lon, provider


def _atomic_write(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def set_cached_geocode(
    address: str,
    lat: float,
    lon: float,
    provider: str,
    *,
    base_dir: Path | str | None = None,
) -> None:
    """Persist a geocoding result on disk using an atomic write."""

    target = _cache_file(address, base_dir)
    payload = {
        "ts": time.time(),
        "lat": lat,
        "lon": lon,
        "provider": provider,
        "address": normalize_address(address),
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    _atomic_write(target, serialized)


__all__: Iterable[str] = [
    "cache_key",
    "get_cached_geocode",
    "normalize_address",
    "set_cached_geocode",
]
