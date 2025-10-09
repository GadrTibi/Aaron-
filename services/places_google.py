from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Iterable

import requests


EARTH_RADIUS_M = 6_371_000.0
BASE = "https://places.googleapis.com/v1"
FIELD_MASK = "places.id,places.displayName,places.primaryType,places.types,places.location,places.shortFormattedAddress"


@dataclass(slots=True)
class GPlace:
    name: str
    place_id: str
    lat: float
    lon: float
    distance_m: float
    types: list[str]
    raw: dict


class GooglePlacesError(RuntimeError):
    """Custom error containing Google Places response details."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = body


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def dedup_and_cut(items: Iterable[GPlace], limit: int) -> list[GPlace]:
    sorted_items = sorted(items, key=lambda p: p.distance_m)
    seen_ids: set[str] = set()
    seen_geo: set[tuple[str, float, float]] = set()
    result: list[GPlace] = []
    for place in sorted_items:
        pid = place.place_id
        if pid and pid in seen_ids:
            continue
        geo_key = (place.name.strip().lower(), round(place.lat, 6), round(place.lon, 6))
        if geo_key in seen_geo:
            continue
        if pid:
            seen_ids.add(pid)
        seen_geo.add(geo_key)
        result.append(place)
        if limit and len(result) >= limit:
            break
    return result


class GooglePlacesService:
    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("Google Places API key is required")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{BASE}/{endpoint}"
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "Content-Type": "application/json",
        }
        attempts = 3
        base_delay = 0.8
        for attempt in range(attempts):
            try:
                response = self.session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10,
                )
            except requests.RequestException as exc:
                if attempt < attempts - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Google Places request failed: {exc}") from exc

            status = response.status_code
            if status < 400:
                try:
                    return response.json()
                except ValueError as exc:
                    raise RuntimeError("Google Places error invalid JSON response") from exc

            retryable = status == 429 or 500 <= status < 600
            if retryable and attempt < attempts - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                time.sleep(delay)
                continue

            message = self._extract_error_message(response)
            raise RuntimeError(f"Google Places error {status}: {message}")

        raise RuntimeError("Google Places error: max retries exceeded")

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            text = (response.text or "").strip()
            return text[:300] if text else "Unknown error"
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
        text = (response.text or "").strip()
        if text:
            return text[:300]
        return "Unknown error"

    def _search_nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        included_types: list[str],
        max_results: int,
    ) -> list[dict]:
        cleaned_types = [t.strip() for t in included_types if isinstance(t, str) and t.strip()]
        if not cleaned_types:
            raise ValueError("included_types must contain at least one type")

        payload = {
            "includedTypes": cleaned_types,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(radius_m),
                }
            },
            "maxResultCount": max(1, min(50, int(max_results))),
            "languageCode": "fr",
        }
        data = self._post("places:searchNearby", payload)
        return data.get("places", []) or []

    def _search_text(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        text_query: str,
        included_types: list[str] | None,
        max_results: int,
    ) -> list[dict]:
        query = str(text_query).strip()
        if not query:
            raise ValueError("text_query must not be empty")
        payload = {
            "textQuery": query,
            "includedTypes": [
                t.strip()
                for t in (included_types or [])
                if isinstance(t, str) and t.strip()
            ],
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(radius_m),
                }
            },
            "maxResultCount": max(1, min(50, int(max_results))),
            "languageCode": "fr",
        }
        data = self._post("places:searchText", payload)
        return data.get("places", []) or []

    @staticmethod
    def _to_places(lat: float, lon: float, places: Iterable[dict]) -> list[GPlace]:
        results: list[GPlace] = []
        for place in places:
            if not isinstance(place, dict):
                continue
            display_name = place.get("displayName")
            name: str | None = None
            if isinstance(display_name, dict):
                text = display_name.get("text")
                if isinstance(text, str) and text.strip():
                    name = text.strip()
            if not name:
                fallback = place.get("name") or place.get("id") or "Sans nom"
                name = str(fallback)
            location = place.get("location") or {}
            plat = location.get("latitude")
            plon = location.get("longitude")
            if plat is None or plon is None:
                continue
            try:
                plat_f = float(plat)
                plon_f = float(plon)
            except (TypeError, ValueError):
                continue
            distance = _haversine(lat, lon, plat_f, plon_f)
            types = [t for t in (place.get("types") or []) if isinstance(t, str)]
            results.append(
                GPlace(
                    name=name,
                    place_id=str(place.get("id", "")),
                    lat=plat_f,
                    lon=plon_f,
                    distance_m=distance,
                    types=types,
                    raw=place,
                )
            )
        return results

    def _nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        included_types: list[str],
        limit: int,
    ) -> list[GPlace]:
        limit = max(0, int(limit))
        max_results = limit * 3 if limit else 50
        raw_places = self._search_nearby(lat, lon, radius_m, included_types, max_results)
        places = self._to_places(lat, lon, raw_places)
        return dedup_and_cut(places, limit)

    def list_incontournables(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int = 15,
    ) -> list[GPlace]:
        included = [
            "restaurant",
            "cafe",
            "bakery",
            "bar",
            "meal_takeaway",
            "shopping_mall",
            "department_store",
            "supermarket",
        ]
        return self._nearby(lat, lon, radius_m, included, limit)

    def list_spots(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int = 10,
    ) -> list[GPlace]:
        included = ["park", "tourist_attraction", "point_of_interest"]
        r1 = self._search_nearby(lat, lon, radius_m, included, limit * 2)
        r2 = self._search_text(lat, lon, radius_m, "belvédère", included, limit)
        r3 = self._search_text(lat, lon, radius_m, "rooftop panorama", included, limit)
        r4 = self._search_text(lat, lon, radius_m, "plage beach", included, limit)
        places = (
            self._to_places(lat, lon, r1)
            + self._to_places(lat, lon, r2)
            + self._to_places(lat, lon, r3)
            + self._to_places(lat, lon, r4)
        )
        return dedup_and_cut(places, limit)

    def list_visits(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int = 10,
    ) -> list[GPlace]:
        included = [
            "museum",
            "art_gallery",
            "tourist_attraction",
            "church",
            "cathedral",
            "palace",
            "castle",
            "zoo",
            "amusement_park",
            "botanical_garden",
        ]
        raw_places = self._search_nearby(lat, lon, radius_m, included, limit * 3)
        places = self._to_places(lat, lon, raw_places)
        return dedup_and_cut(places, limit)


__all__ = ["GPlace", "GooglePlacesService", "dedup_and_cut", "GooglePlacesError"]
