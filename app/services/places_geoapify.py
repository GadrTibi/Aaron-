from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List

import requests

from config import places_settings

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Place:
    name: str
    lat: float
    lon: float
    distance_m: float
    category: str
    raw: Dict[str, Any]


class GeoapifyPlacesService:
    """Client for the Geoapify Places API."""

    BASE_URL = "https://api.geoapify.com/v2/places"
    CACHE_TTL_SECONDS = 48 * 3600
    _PAGE_SLEEP_SECONDS = 0.12

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key if api_key is not None else places_settings.GEOAPIFY_API_KEY
        if not key:
            raise ValueError("GEOAPIFY_API_KEY manquant")
        self.api_key = key
        self._session = requests.Session()
        self._session.headers.update(places_settings.build_headers())

    def list_incontournables(
        self, lat: float, lon: float, radius_m: int, limit: int = 15
    ) -> List[Place]:
        categories = [
            "catering.restaurant",
            "catering.cafe",
            "catering.fast_food",
            "commercial.department_store",
            "commercial.shopping_mall",
            "commercial.supermarket",
            "commercial.shop",
        ]
        return self._list_places(lat, lon, radius_m, limit, "incontournables", categories)

    def list_spots(
        self, lat: float, lon: float, radius_m: int, limit: int = 10
    ) -> List[Place]:
        categories = [
            "tourism.viewpoint",
            "leisure.park",
            "leisure.garden",
            "natural.beach",
            "leisure.nature_reserve",
            "natural.cliff",
            "natural.peak",
            "attraction",
        ]
        return self._list_places(lat, lon, radius_m, limit, "spots", categories)

    def _list_places(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int,
        category: str,
        categories: Iterable[str],
    ) -> List[Place]:
        cache_key = f"geoapify:{category}:{round(lat, 5)}:{round(lon, 5)}:{radius_m}:{limit}"
        cached = places_settings.read_cache_json(cache_key, self.CACHE_TTL_SECONDS)
        if cached:
            return [Place(**entry) for entry in cached]

        try:
            places = self._fetch_places(lat, lon, radius_m, limit, category, categories)
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning("Geoapify Places failure: %s", exc)
            return []

        if places:
            places_settings.write_cache_json(cache_key, [asdict(place) for place in places])
        return places

    def _fetch_places(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int,
        category: str,
        categories: Iterable[str],
    ) -> List[Place]:
        collected: List[Place] = []
        seen: set[str | tuple[str | None, float, float]] = set()
        offsets = [0, 100]
        params_base = {
            "categories": ",".join(categories),
            "filter": f"circle:{lon},{lat},{radius_m}",
            "limit": 100,
            "apiKey": self.api_key,
        }

        for offset in offsets:
            if len(collected) >= limit:
                break

            payload = {**params_base, "offset": offset} if offset else dict(params_base)
            response = self._request_json(self.BASE_URL, payload)
            if response is None:
                break

            features = response.get("features", [])
            if not features:
                break

            for feature in features:
                properties: Dict[str, Any] = feature.get("properties", {})
                geometry: Dict[str, Any] = feature.get("geometry", {})
                coordinates = geometry.get("coordinates") or [None, None]
                lon2, lat2 = coordinates[0], coordinates[1]
                if lat2 is None or lon2 is None:
                    continue

                place_id = properties.get("place_id")
                if place_id:
                    unique_id: str | tuple[str | None, float, float] = str(place_id)
                else:
                    unique_id = (
                        properties.get("name"),
                        round(float(lat2), 6),
                        round(float(lon2), 6),
                    )
                if unique_id in seen:
                    continue
                seen.add(unique_id)

                distance = self._compute_distance(
                    lat, lon, float(lat2), float(lon2), properties.get("distance")
                )
                name = properties.get("name") or properties.get("formatted") or "Lieu"  # fallback
                collected.append(
                    Place(
                        name=name,
                        lat=float(lat2),
                        lon=float(lon2),
                        distance_m=distance,
                        category=category,
                        raw=feature,
                    )
                )

            if offset == 0:
                if len(features) == 100 and len(collected) < limit:
                    time.sleep(self._PAGE_SLEEP_SECONDS)
                else:
                    break

        collected.sort(key=lambda place: place.distance_m)
        return collected[:limit]

    def _request_json(self, url: str, params: Dict[str, Any]) -> Dict[str, Any] | None:
        retries = places_settings.RETRIES
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._session.get(url, params=params, timeout=places_settings.HTTP_TIMEOUT)
                if response.status_code in {429} or response.status_code >= 500:
                    raise requests.HTTPError(f"{response.status_code}", response=response)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                if attempt > retries:
                    LOGGER.warning("Geoapify request failed after retries: %s", exc)
                    return None
                self._sleep_with_backoff(attempt)

    def _sleep_with_backoff(self, attempt: int) -> None:
        delay = places_settings.RETRY_BASE_DELAY * (2 ** (attempt - 1))
        delay += random.uniform(0, places_settings.RETRY_JITTER)
        time.sleep(delay)

    @staticmethod
    def _compute_distance(
        lat1: float, lon1: float, lat2: float, lon2: float, provided: Any
    ) -> float:
        try:
            if provided is not None:
                value = float(provided)
                if value >= 0:
                    return value
        except (TypeError, ValueError):
            pass

        rad_lat1 = math.radians(lat1)
        rad_lat2 = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        a = math.sin(delta_lat / 2) ** 2 + math.cos(rad_lat1) * math.cos(rad_lat2) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return 6371000 * c
