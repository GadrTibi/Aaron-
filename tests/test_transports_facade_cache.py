import types

import app.services.transports_facade as facade


def test_get_transports_cached(monkeypatch):
    call_count = {"calls": 0}

    def fake_fetch(lat, lon, radius, mode, has_google):
        call_count["calls"] += 1
        return {"metro_lines": ["A"], "bus_lines": ["B"], "taxis": [], "provider_used": {}, "warnings": [], "debug": {}}

    monkeypatch.setattr(facade, "_fetch_transports", fake_fetch)
    facade.clear_transport_cache()

    first = facade.get_transports(1.23456, 2.34567, radius_m=500, mode="FAST")
    second = facade.get_transports(1.23456, 2.34567, radius_m=500, mode="FAST")

    assert call_count["calls"] == 1
    assert first["cache_status"] == "MISS"
    assert second["cache_status"] == "HIT"
