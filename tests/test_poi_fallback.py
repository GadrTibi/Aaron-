from app.services.generation_report import GenerationReport
from app.services import poi_facade


class DummyGeoapify:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def list_incontournables(self, lat, lon, radius_m, limit=15):
        item = type("Obj", (), {"name": "Geo Spot", "distance_m": 12.0})
        return [item]

    def list_spots(self, lat, lon, radius_m, limit=10):
        return []


def test_poi_fallback_to_geoapify(monkeypatch):
    monkeypatch.setattr(
        poi_facade,
        "get_provider_status",
        lambda: {
            "Google Places": {"enabled": False},
            "Geoapify": {"enabled": True},
        },
    )
    monkeypatch.setattr(poi_facade, "resolve_geoapify_key", lambda: ("token", "env"))
    monkeypatch.setattr(poi_facade, "GeoapifyPlacesService", DummyGeoapify)

    report = GenerationReport()
    results = poi_facade.get_pois(
        lat=1.0,
        lon=2.0,
        radius_m=500,
        categories=("incontournables", "spots"),
        report=report,
    )

    assert results["incontournables"]
    assert results["incontournables"][0].name == "Geo Spot"
    assert any("Fallback POI utilisé" in warn or "Google Places non disponible" in warn for warn in report.provider_warnings)
