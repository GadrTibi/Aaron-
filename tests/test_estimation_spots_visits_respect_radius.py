from app.services import poi_facade


class DummyGooglePlaces:
    def __init__(self, api_key):
        self.api_key = api_key

    def list_incontournables(self, lat, lon, radius_m, limit=15):
        return []

    def list_spots(self, lat, lon, radius_m, limit=10):
        near = type("Obj", (), {"name": "Spot proche", "distance_m": 120.0})
        far = type("Obj", (), {"name": "Spot loin", "distance_m": 420.0})
        return [near, far]

    def list_visits(self, lat, lon, radius_m, limit=10):
        near = type("Obj", (), {"name": "Visite proche", "distance_m": 200.0})
        far = type("Obj", (), {"name": "Visite loin", "distance_m": 600.0})
        return [near, far]


def test_build_spots_and_visits_respects_radius(monkeypatch):
    monkeypatch.setattr(
        poi_facade,
        "get_provider_status",
        lambda: {"Google Places": {"enabled": True}},
    )
    monkeypatch.setattr(poi_facade, "resolve_google_key", lambda: ("token", "env"))
    monkeypatch.setattr(poi_facade, "GooglePlacesService", DummyGooglePlaces)

    results = poi_facade.build_spots_and_visits(lat=48.0, lon=2.0, radius_m=300)

    assert [item.name for item in results["spots"]] == ["Spot proche"]
    assert [item.name for item in results["visits"]] == ["Visite proche"]
