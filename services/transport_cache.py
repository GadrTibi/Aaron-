"""Persistent cache for automatic transport lookups."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterable, Tuple


DEFAULT_CACHE_DIR = Path(os.getenv("MFY_TRANSPORT_CACHE_DIR", "out/cache/transports"))


def _normalize_float(value: float, *, rounding: int = 4) -> float:
    try:
        return round(float(value), rounding)
    except Exception:
        return 0.0


def _key(lat: float, lon: float, radius_m: int, provider_order: Iterable[str], *, rounding: int) -> str:
    providers = ",".join(provider_order)
    return f"{_normalize_float(lat, rounding=rounding)}:{_normalize_float(lon, rounding=rounding)}:{int(radius_m)}:{providers}"


def _cache_file(key: str, base_dir: Path | str | None = None) -> Path:
    folder = Path(base_dir) if base_dir is not None else DEFAULT_CACHE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{key}.json"


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


class TransportCache:
    """Lightweight disk cache for TransportService auto calls."""

    def __init__(self, base_dir: Path | str | None = None, *, ttl_seconds: float | None = None, rounding: int = 4) -> None:
        self.base_dir = base_dir
        default_ttl = float(os.getenv("MFY_TRANSPORT_CACHE_TTL", 7 * 24 * 3600))
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else default_ttl
        self.rounding = rounding

    def get(self, lat: float, lon: float, radius_m: int, provider_order: Iterable[str]) -> dict | None:
        cache_id = _key(lat, lon, radius_m, provider_order, rounding=self.rounding)
        target = _cache_file(cache_id, self.base_dir)
        if not target.exists():
            return None
        data = _read_json(target)
        if _is_expired(data.get("ts", 0), self.ttl_seconds):
            return None
        return data.get("payload")

    def set(self, lat: float, lon: float, radius_m: int, provider_order: Iterable[str], payload: dict) -> None:
        cache_id = _key(lat, lon, radius_m, provider_order, rounding=self.rounding)
        target = _cache_file(cache_id, self.base_dir)
        content = {"ts": time.time(), "payload": payload}
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
            tmp.replace(target)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass


__all__: Tuple[str, ...] = ("TransportCache",)
