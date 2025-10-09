from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Iterable

import requests


EARTH_RADIUS_M = 6_371_000.0


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
    _URL = "https://places.googleapis.com/v1/places:searchNearby"
    _FIELD_MASK = (
        "places.id,"
        "places.displayName,"
        "places.location,"
        "places.types,"
        "places.primaryType,"
        "places.shortFormattedAddress"
    )

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("Google Places API key is required")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _request(self, payload: dict) -> dict:
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": self._FIELD_MASK,
            "Content-Type": "application/json",
        }
        base_delay = 0.8
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    self._URL,
                    headers=headers,
                    json=payload,
                    timeout=10,
                )
            except requests.RequestException as exc:
                if attempt < max_attempts - 1:
                    delay = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                    time.sleep(delay)
                    continue
                raise GooglePlacesError(
                    f"Google Places request failed: {exc}",
                ) from exc

            status = response.status_code
            if status < 400:
                try:
                    return response.json()
                except ValueError as exc:
                    raise GooglePlacesError("Google Places API returned invalid JSON") from exc

            retryable = status == 429 or 500 <= status < 600
            if retryable and attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                time.sleep(delay)
                continue

            error_hint = self._explain_bad_request(response)
            body_snippet = (response.text or "")[:500].strip()
            details_parts: list[str] = []
            if error_hint:
                details_parts.append(error_hint)
            if body_snippet and (not error_hint or error_hint not in body_snippet):
                details_parts.append(body_snippet)
            details = " | ".join(details_parts) if details_parts else body_snippet or "Unknown error"
            raise GooglePlacesError(
                f"Google Places API error ({status}): {details}",
                status_code=status,
                body=body_snippet,
            )

        raise GooglePlacesError("Google Places API error: max retries exceeded")

    @staticmethod
    def _explain_bad_request(response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return ""
        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return ""
        message = error.get("message")
        if isinstance(message, str):
            return message
        return ""

    def _nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        included_types: list[str],
        keyword: str | None = None,
        limit: int = 50,
    ) -> list[GPlace]:
        cleaned_types = [t for t in included_types if isinstance(t, str) and t.strip()]
        if not cleaned_types:
            raise ValueError("included_types must contain at least one type")

        radius = float(radius_m)
        radius = max(50.0, min(50000.0, radius))

        limit = max(0, int(limit))
        max_result_count = min(50, max(1, limit * 3 if limit else 50))

        payload: dict = {
            "includedTypes": cleaned_types,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": radius,
                }
            },
            "maxResultCount": max_result_count,
            "languageCode": "fr",
        }
        if keyword:
            payload["textQuery"] = keyword

        data = self._request(payload)
        places = data.get("places", []) or []
        results: list[GPlace] = []
        for place in places:
            display_name = (
                place.get("displayName", {}).get("text")
                or place.get("name")
                or "Sans nom"
            )
            place_id = place.get("id", "")
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
                    name=display_name,
                    place_id=str(place_id),
                    lat=plat_f,
                    lon=plon_f,
                    distance_m=distance,
                    types=types,
                    raw=place,
                )
            )
        return dedup_and_cut(results, limit)

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
        return self._nearby(lat, lon, radius_m, included, None, limit)

    def list_spots(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int = 10,
    ) -> list[GPlace]:
        included = ["park", "tourist_attraction", "point_of_interest"]
        l1 = self._nearby(lat, lon, radius_m, included, None, limit * 3)
        l2 = self._nearby(lat, lon, radius_m, included, "belvédère", limit)
        l3 = self._nearby(lat, lon, radius_m, included, "rooftop panorama", limit)
        l4 = self._nearby(lat, lon, radius_m, included, "plage beach", limit)
        return dedup_and_cut(l1 + l2 + l3 + l4, limit)

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
        return self._nearby(lat, lon, radius_m, included, None, limit)


__all__ = ["GPlace", "GooglePlacesService", "dedup_and_cut", "GooglePlacesError"]
