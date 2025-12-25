import app.services.transports_facade as facade


def test_normalize_name_and_deduplication():
    names = ["Ligne 12", "  ligne 12 ", "bus 12", "Bus 12"]
    deduped = facade._dedupe_labels(names, limit=10)

    assert deduped == ["Ligne 12"]


def test_max_results_limit():
    labels = [f"Station {i}" for i in range(10)]
    limited = facade._dedupe_labels(labels)

    assert len(limited) == facade._MAX_RESULTS
    assert limited[0].startswith("Station 0")


def test_fast_mode_labels_without_ligne(monkeypatch):
    def fake_overpass(lat, lon, radius):
        return {
            "metro_lines": ["Station Alpha (120 m)", "Station Beta (200 m)"],
            "bus_lines": ["Arrêt Gamma (80 m)"],
            "warnings": [],
            "debug": {},
            "raw_counts": {"metro": 2, "bus": 1},
        }

    monkeypatch.setattr(facade, "_fetch_overpass_data", fake_overpass)
    monkeypatch.setattr(facade, "_google_api_key", lambda: "")
    facade.clear_transport_cache()

    result = facade.get_transports(10.0, 20.0, mode="FAST")

    assert all(not line.lower().startswith("ligne ") for line in result["metro_lines"])
    assert all(not line.lower().startswith("ligne ") for line in result["bus_lines"])
    assert result["taxis"] == ["Non calculé (mode FAST)"]


def test_overpass_limit_to_four_items(monkeypatch):
    def fake_query_overpass(query):
        is_bus = "bus_stop" in query
        elements = []
        for i in range(100):
            elements.append(
                {
                    "lat": 48.0 + 0.0001 * i,
                    "lon": 2.0,
                    "tags": {"name": f"{'Bus' if is_bus else 'Station'} {i}", "highway": "bus_stop" if is_bus else "railway"},
                }
            )
        return elements, {"status": "ok", "items": len(elements)}

    monkeypatch.setattr(facade, "_query_overpass_points", fake_query_overpass)
    monkeypatch.setattr(facade, "_google_api_key", lambda: "")
    facade.clear_transport_cache()

    result = facade.get_transports(48.0, 2.0, mode="FAST")

    assert len(result["metro_lines"]) == facade._MAX_RESULTS
    assert len(result["bus_lines"]) == facade._MAX_RESULTS
