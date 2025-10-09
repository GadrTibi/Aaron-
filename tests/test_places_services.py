from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import requests

from config import places_settings
from services.places_geoapify import GeoapifyPlacesService
from services.places_otm import OpenTripMapService


class FakeResponse:
    def __init__(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"Status {self.status_code}")


@pytest.fixture(autouse=True)
def patch_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(places_settings, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(GeoapifyPlacesService, "_PAGE_SLEEP_SECONDS", 0.0)


def _geo_feature(idx: int, distance: float) -> Dict[str, Any]:
    return {
        "properties": {"place_id": f"id-{idx}", "name": f"Place {idx}", "distance": distance},
        "geometry": {"coordinates": [2.0 + idx * 0.001, 48.0 + idx * 0.001]},
    }


def _otm_feature(idx: int, distance: float) -> Dict[str, Any]:
    return {
        "properties": {
            "xid": f"XID{idx}",
            "name": f"Visit {idx}",
            "kinds": "museums,art_galleries",
            "dist": distance,
        },
        "geometry": {"coordinates": [2.0 + idx * 0.01, 48.0 + idx * 0.01]},
    }


def test_geoapify_lists_sorted_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    service = GeoapifyPlacesService(api_key="token")

    first_page = [_geo_feature(idx, float(idx * 10)) for idx in range(100)]
    # Inject duplicates on the first page
    first_page[10]["properties"]["place_id"] = "id-0"
    first_page[20]["properties"]["place_id"] = "id-5"

    calls: List[Dict[str, Any]] = []

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> FakeResponse:
        calls.append(params)
        offset = params.get("offset", 0)
        if offset == 0:
            return FakeResponse({"features": first_page})
        return FakeResponse({"features": []})

    monkeypatch.setattr(service._session, "get", fake_get)

    results = service.list_incontournables(48.0, 2.0, 2000, limit=15)
    assert len(results) == 15
    assert [place.category for place in results] == ["incontournables"] * 15
    assert [place.name for place in results[:3]] == ["Place 0", "Place 1", "Place 2"]
    assert all(results[idx].distance_m <= results[idx + 1].distance_m for idx in range(len(results) - 1))
    assert len(calls) == 1
    unique_ids = {place.raw["properties"].get("place_id") for place in results}
    assert len(unique_ids) == len(results)

    cache_files = list(Path(places_settings.CACHE_DIR).glob("*.json"))
    assert cache_files, "Expected cache file to be created"

    calls_before = len(calls)

    def fail_get(*_: Any, **__: Any) -> None:
        raise AssertionError("Cache should prevent HTTP call")

    monkeypatch.setattr(service._session, "get", fail_get)
    cached_results = service.list_incontournables(48.0, 2.0, 2000, limit=15)
    assert len(cached_results) == 15
    assert cached_results[0].name == "Place 0"
    assert len(calls) == calls_before

    # Spots should fetch new data and cut at 10 items
    monkeypatch.setattr(service._session, "get", fake_get)
    spots = service.list_spots(48.0, 2.0, 2000, limit=10)
    assert len(spots) == 10
    assert all(place.category == "spots" for place in spots)


def test_otm_lists_limited_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    service = OpenTripMapService(api_key="token")

    features = [_otm_feature(idx, float(50 + idx * 5)) for idx in range(60)]
    calls: List[str] = []

    def fake_get(url: str, params: Dict[str, Any], timeout: int) -> FakeResponse:
        calls.append(url)
        if "radius" in url:
            return FakeResponse({"features": features})
        if "/xid/" in url:
            pytest.fail("Detail endpoint should not be called when data is complete")
        return FakeResponse({"features": []})

    monkeypatch.setattr(service._session, "get", fake_get)

    visits = service.list_visits(48.5, 2.4, 3000, limit=10)
    assert len(visits) == 10
    assert [visit.name for visit in visits[:3]] == ["Visit 0", "Visit 1", "Visit 2"]
    assert all(visits[idx].distance_m <= visits[idx + 1].distance_m for idx in range(len(visits) - 1))
    assert calls.count(f"{service.BASE_URL}/{service.lang}/places/radius") == 1

    calls_before = len(calls)

    def fail_get(*_: Any, **__: Any) -> None:
        raise AssertionError("Cache should prevent HTTP call")

    monkeypatch.setattr(service._session, "get", fail_get)
    cached = service.list_visits(48.5, 2.4, 3000, limit=10)
    assert len(cached) == 10
    assert len(calls) == calls_before


def test_missing_api_key() -> None:
    with pytest.raises(ValueError):
        GeoapifyPlacesService(api_key="")
    with pytest.raises(ValueError):
        OpenTripMapService(api_key="")


def test_timeout_retries(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    service = GeoapifyPlacesService(api_key="token")

    def raise_timeout(*_: Any, **__: Any) -> None:
        raise requests.Timeout("Timeout")

    monkeypatch.setattr(service, "_sleep_with_backoff", lambda attempt: None)
    monkeypatch.setattr(service._session, "get", raise_timeout)

    with caplog.at_level("WARNING"):
        results = service.list_incontournables(10.0, 20.0, 1000, limit=5)
    assert results == []
    assert "failed" in caplog.text
