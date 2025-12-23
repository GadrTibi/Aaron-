from services.transport_cache import TransportCache


def test_transport_cache_hit(tmp_path):
    cache = TransportCache(base_dir=tmp_path, ttl_seconds=1000, rounding=4)
    payload = {"metro_lines": ["A"], "bus_lines": ["1"], "taxis": ["Foo"], "provider_used": {"metro": "gtfs"}}
    cache.set(48.0, 2.0, 1200, ("gtfs", "osm"), payload)
    cached = cache.get(48.0, 2.0, 1200, ("gtfs", "osm"))
    assert cached == payload


def test_transport_cache_expired(tmp_path, monkeypatch):
    cache = TransportCache(base_dir=tmp_path, ttl_seconds=10, rounding=4)
    payload = {"metro_lines": ["B"], "bus_lines": [], "taxis": [], "provider_used": {}}
    monkeypatch.setattr("services.transport_cache.time.time", lambda: 0)
    cache.set(10.0, 20.0, 500, ("gtfs",), payload)
    monkeypatch.setattr("services.transport_cache.time.time", lambda: 20)
    assert cache.get(10.0, 20.0, 500, ("gtfs",)) is None
