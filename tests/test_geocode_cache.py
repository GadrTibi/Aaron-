import json
from pathlib import Path

from app.services import geocode_cache


def test_geocode_cache_hit(tmp_path):
    geocode_cache.set_cached_geocode("10 rue test", 1.23, 4.56, "Nominatim", base_dir=tmp_path)
    cached = geocode_cache.get_cached_geocode("10 rue test", base_dir=tmp_path, ttl_seconds=3600)
    assert cached == (1.23, 4.56, "Nominatim")


def test_geocode_cache_expired(tmp_path, monkeypatch):
    base_dir = tmp_path
    # freeze time for deterministic ttl
    monkeypatch.setattr(geocode_cache.time, "time", lambda: 1000.0)
    geocode_cache.set_cached_geocode("12 avenue future", 7.0, 8.0, "Geoapify", base_dir=base_dir)

    # advance time beyond TTL
    monkeypatch.setattr(geocode_cache.time, "time", lambda: 1000.0 + 31 * 24 * 3600 + 10)
    expired = geocode_cache.get_cached_geocode("12 avenue future", base_dir=base_dir, ttl_seconds=30 * 24 * 3600)
    assert expired is None
