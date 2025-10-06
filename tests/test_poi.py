from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from app.services.poi_fetcher import FetchResult, OverpassClient, OverpassError, POIService


class DummyWikipedia:
    def __init__(self, items: List[Dict[str, Any]]) -> None:
        self.items = items
        self.calls = 0

    def fetch(self, lat: float, lon: float, radius_m: int, *, lang: str = "fr") -> FetchResult:
        self.calls += 1
        return FetchResult(
            items=list(self.items),
            provider="wikipedia",
            endpoint=f"https://{lang}.wikipedia.org/w/api.php",
            status=200,
        )


class DummyOverpassFail:
    def __init__(self) -> None:
        self.calls = 0
        self.attempts = [
            {"endpoint": OverpassClient.ENDPOINTS[0], "status": 504},
            {"endpoint": OverpassClient.ENDPOINTS[1], "status": 429},
        ]

    def fetch(self, lat: float, lon: float, radius_m: int, category: str, *, lang: str = "fr") -> FetchResult:
        self.calls += 1
        raise OverpassError("failure", self.attempts)


class DummyOverpassSuccess:
    def __init__(self, *, lat_offset: float = 0.001, lon_offset: float = 0.001) -> None:
        self.calls = 0
        self.lat_offset = lat_offset
        self.lon_offset = lon_offset

    def fetch(self, lat: float, lon: float, radius_m: int, category: str, *, lang: str = "fr") -> FetchResult:
        self.calls += 1
        return FetchResult(
            items=[
                {
                    "id": 1,
                    "name": "Tour Eiffel",
                    "lat": lat + self.lat_offset,
                    "lon": lon + self.lon_offset,
                    "tags": {"tourism": "attraction"},
                }
            ],
            provider="overpass",
            endpoint=OverpassClient.ENDPOINTS[0],
            status=200,
            duration_ms=120.0,
        )


def test_poi_fallback_to_wikipedia(tmp_path: Path) -> None:
    overpass = DummyOverpassFail()
    wikipedia = DummyWikipedia(
        [
            {
                "id": 100,
                "name": "Champ de Mars",
                "lat": 48.855,
                "lon": 2.298,
                "tags": {"source": "wikipedia"},
            }
        ]
    )
    service = POIService(overpass_client=overpass, wikipedia_client=wikipedia, cache_dir=tmp_path)

    items = service.get_pois(48.8583, 2.2945, radius_m=1500, category="incontournables")

    assert overpass.calls == 1
    assert wikipedia.calls == 1
    assert service.last_result is not None
    assert service.last_result.provider == "wikipedia"
    assert items[0]["source"] == "wikipedia"
    statuses = {attempt.get("status") for attempt in overpass.attempts}
    assert {504, 429} <= statuses


def test_poi_overpass_success_and_cache(tmp_path: Path) -> None:
    overpass = DummyOverpassSuccess()
    wikipedia = DummyWikipedia([])
    service = POIService(overpass_client=overpass, wikipedia_client=wikipedia, cache_dir=tmp_path)

    items_first = service.get_pois(48.8583, 2.2945, radius_m=1200, category="spots")
    assert overpass.calls == 1
    assert wikipedia.calls == 0
    assert items_first
    assert items_first[0]["source"] == "overpass"
    assert items_first[0]["distance"] is not None

    cache_files = list(tmp_path.glob("*.json"))
    assert cache_files, "cache should be written"

    items_second = service.get_pois(48.8583, 2.2945, radius_m=1200, category="spots")
    assert overpass.calls == 1, "second call must use cache"
    assert wikipedia.calls == 0
    assert items_second == items_first


def test_poi_cache_ttl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    overpass = DummyOverpassSuccess()
    wikipedia = DummyWikipedia([])
    service = POIService(overpass_client=overpass, wikipedia_client=wikipedia, cache_dir=tmp_path)

    class TimeStub:
        def __init__(self) -> None:
            self.value = 0.0

        def time(self) -> float:
            return self.value

    time_stub = TimeStub()
    monkeypatch.setattr("app.services.poi_fetcher.time.time", time_stub.time)

    service.get_pois(48.8583, 2.2945, radius_m=800, category="spots")
    assert overpass.calls == 1

    time_stub.value = POIService.CACHE_TTL_SECONDS - 60
    service.get_pois(48.8583, 2.2945, radius_m=800, category="spots")
    assert overpass.calls == 1, "cache still valid"

    time_stub.value = POIService.CACHE_TTL_SECONDS + 1
    service.get_pois(48.8583, 2.2945, radius_m=800, category="spots")
    assert overpass.calls == 2, "cache expired triggers refresh"
