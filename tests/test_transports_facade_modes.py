import app.services.transports_facade as facade


def _base_overpass():
    return {"metro_lines": ["M1"], "bus_lines": ["B1"], "warnings": [], "debug": {}}


def test_fast_mode_skips_google_and_gtfs(monkeypatch):
    calls = {"overpass": 0, "google": 0, "gtfs": 0}

    def fake_overpass(lat, lon, radius):
        calls["overpass"] += 1
        return _base_overpass()

    def fake_google(lat, lon, radius, api_key):
        calls["google"] += 1
        return {"metro_lines": ["G1"], "bus_lines": ["G2"], "warnings": [], "debug": {}}

    def fake_gtfs(lat, lon, radius, metro, bus):
        calls["gtfs"] += 1
        return metro, bus

    monkeypatch.setattr(facade, "_fetch_overpass_data", fake_overpass)
    monkeypatch.setattr(facade, "_enrich_with_google", fake_google)
    monkeypatch.setattr(facade, "_apply_gtfs_enrichment", fake_gtfs)
    monkeypatch.setattr(facade, "_google_api_key", lambda: "key")
    facade.clear_transport_cache()

    result = facade.get_transports(10.0, 20.0, mode="FAST")

    assert calls["overpass"] == 1
    assert calls["google"] == 0
    assert calls["gtfs"] == 0
    assert result["metro_lines"] == ["M1"]
    assert result["bus_lines"] == ["B1"]


def test_enriched_uses_google_when_key(monkeypatch):
    calls = {"google": 0}

    monkeypatch.setattr(facade, "_fetch_overpass_data", lambda lat, lon, radius: _base_overpass())

    def fake_google(lat, lon, radius, api_key):
        calls["google"] += 1
        return {"metro_lines": ["G1"], "bus_lines": ["G2"], "warnings": [], "debug": {}}

    monkeypatch.setattr(facade, "_enrich_with_google", fake_google)
    monkeypatch.setattr(facade, "_apply_gtfs_enrichment", lambda lat, lon, radius, metro, bus: (metro, bus))
    monkeypatch.setattr(facade, "_google_api_key", lambda: "key")
    facade.clear_transport_cache()

    result = facade.get_transports(10.0, 20.0, mode="ENRICHED")

    assert calls["google"] == 1
    assert any("G1" in line for line in result["metro_lines"])
    assert any("G2" in line for line in result["bus_lines"])


def test_full_adds_gtfs(monkeypatch):
    calls = {"gtfs": 0}

    monkeypatch.setattr(facade, "_fetch_overpass_data", lambda lat, lon, radius: _base_overpass())
    monkeypatch.setattr(facade, "_enrich_with_google", lambda lat, lon, radius, api_key: {"metro_lines": [], "bus_lines": [], "warnings": [], "debug": {}})

    def fake_gtfs(lat, lon, radius, metro, bus):
        calls["gtfs"] += 1
        return metro + ["GTFS-M"], bus + ["GTFS-B"]

    monkeypatch.setattr(facade, "_apply_gtfs_enrichment", fake_gtfs)
    monkeypatch.setattr(facade, "_google_api_key", lambda: "")
    facade.clear_transport_cache()

    result = facade.get_transports(10.0, 20.0, mode="FULL")

    assert calls["gtfs"] == 1
    assert "GTFS-M" in result["metro_lines"]
    assert "GTFS-B" in result["bus_lines"]
