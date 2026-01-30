from app.services.poi_facade import POIResult, filter_poi_results


def test_filter_poi_results_by_radius():
    results = {
        "spots": [
            POIResult(name="Near Spot", distance_m=100.0, provider="Test", raw=None),
            POIResult(name="Far Spot", distance_m=350.0, provider="Test", raw=None),
        ]
    }

    filtered = filter_poi_results(lat=48.0, lon=2.0, radius_m=300, results=results)

    assert [item.name for item in filtered["spots"]] == ["Near Spot"]
