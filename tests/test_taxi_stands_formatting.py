from app.services.taxi_stands import build_taxi_lines_from_stands, find_nearby_taxi_stands


def test_build_taxi_lines_formats_minutes():
    stands = [{"name": "Place des Ternes", "distance_m": 160}]
    lines = build_taxi_lines_from_stands(stands)
    assert "Station de taxis Place des Ternes (2 min à pied)" in lines


def test_find_nearby_taxi_stands_with_mock(monkeypatch):
    payload = {
        "places": [
            {"displayName": {"text": "Ternes"}, "location": {"latitude": 48.0, "longitude": 2.0}},
            {"displayName": {"text": "Courcelles"}, "location": {"latitude": 48.0005, "longitude": 2.0005}},
        ]
    }

    def fake_request(lat, lon, radius_m, api_key, session=None, timeout=7):
        return payload

    monkeypatch.setattr("app.services.taxi_stands._request_places", fake_request)

    stands = find_nearby_taxi_stands(48.0, 2.0, api_key="dummy")
    assert stands[0]["name"] == "Ternes"
    assert len(stands) <= 2
