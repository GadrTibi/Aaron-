from __future__ import annotations

import math
import random
import re
import time
from dataclasses import dataclass
from typing import Iterable

import requests


EARTH_RADIUS_M = 6_371_000.0
BASE = "https://places.googleapis.com/v1"
FIELD_MASK = "places.id,places.displayName,places.primaryType,places.types,places.location,places.shortFormattedAddress"
MAX_PER_CALL = 20
ALLOWED_TYPES_NEARBY = {
    "restaurant",
    "cafe",
    "bakery",
    "bar",
    "meal_takeaway",
    "shopping_mall",
    "department_store",
    "supermarket",
    "park",
    "tourist_attraction",
    "museum",
    "art_gallery",
    "church",
    "zoo",
    "amusement_park",
    "botanical_garden",
}


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


def _clamp_nearby_types(types: list[str]) -> list[str]:
    return [t for t in types if t in ALLOWED_TYPES_NEARBY]


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
                raise GooglePlacesError(f"Google Places request failed: {exc}") from exc

            status = response.status_code
            if status < 400:
                try:
                    return response.json()
                except ValueError as exc:
                    raise GooglePlacesError(
                        f"Google Places error {status}: invalid JSON response",
                        status_code=status,
                        body=response.text,
                    ) from exc

            retryable = status == 429 or 500 <= status < 600
            if retryable and attempt < attempts - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0.0, 0.5)
                time.sleep(delay)
                continue

            message = self._extract_error_message(response)
            body_text = (response.text or "").strip()[:300]
            raise GooglePlacesError(
                f"Google Places error {status}: {message}",
                status_code=status,
                body=body_text,
            )

        raise GooglePlacesError("Google Places error: max retries exceeded")

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

    @staticmethod
    def _parse_unsupported_types(error_text: str) -> set[str]:
        if not error_text:
            return set()
        pattern = re.compile(r"Unsupported types:\s*([^\n\r.;]+)")
        match = pattern.search(error_text)
        if not match:
            return set()
        types_part = match.group(1)
        types: set[str] = set()
        for chunk in re.split(r"[,\s]+", types_part):
            chunk = chunk.strip().strip("[]'\"")
            if chunk:
                types.add(chunk)
        return types

    def _search_nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        included_types: list[str],
        max_results: int,
    ) -> list[dict]:
        valid_types = _clamp_nearby_types([t.strip() for t in included_types if isinstance(t, str)])
        if not valid_types:
            raise ValueError("No valid includedTypes for Nearby")

        target = max(0, int(max_results))
        if target <= 0:
            return []

        pending_types: list[str] = list(dict.fromkeys(valid_types))
        collected: list[dict] = []
        seen_ids: set[str] = set()

        while pending_types and len(collected) < target:
            current_type = pending_types.pop(0)
            remaining = target - len(collected)
            if remaining <= 0:
                break
            take = min(MAX_PER_CALL, remaining)
            allow_retry = True
            skip_type = False
            while True:
                payload = {
                    "includedTypes": [current_type],
                    "locationRestriction": {
                        "circle": {
                            "center": {"latitude": lat, "longitude": lon},
                            "radius": float(radius_m),
                        }
                    },
                    "maxResultCount": take,
                    "languageCode": "fr",
                }
                try:
                    data = self._post("places:searchNearby", payload)
                except GooglePlacesError as exc:
                    unsupported = set()
                    if exc.status_code == 400:
                        error_text = "\n".join(filter(None, [str(exc), exc.response_body]))
                        unsupported = self._parse_unsupported_types(error_text)
                    if unsupported and allow_retry:
                        allow_retry = False
                        pending_types = [t for t in pending_types if t not in unsupported]
                        if current_type in unsupported:
                            skip_type = True
                            break
                        continue
                    raise
                else:
                    places = data.get("places", []) if isinstance(data, dict) else []
                    for place in places or []:
                        pid = place.get("id")
                        if pid and pid in seen_ids:
                            continue
                        if pid:
                            seen_ids.add(pid)
                        collected.append(place)
                        if len(collected) >= target:
                            break
                    break
            if skip_type:
                continue

        return collected

    def _search_text(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        text_query: str,
        max_results: int,
    ) -> list[dict]:
        query = str(text_query).strip()
        if not query:
            raise ValueError("text_query must not be empty")

        target = max(0, int(max_results))
        if target <= 0:
            return []

        payload = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": float(radius_m),
                }
            },
            "maxResultCount": min(MAX_PER_CALL, target),
            "languageCode": "fr",
        }
        try:
            data = self._post("places:searchText", payload)
        except GooglePlacesError as exc:
            if exc.status_code and exc.status_code >= 400:
                raise RuntimeError(str(exc)) from exc
            raise
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

    def list_incontournables(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int = 15,
    ) -> list[GPlace]:
        limit = max(0, int(limit))
        if limit == 0:
            return []

        types = [
            "restaurant",
            "cafe",
            "bakery",
            "bar",
            "meal_takeaway",
            "shopping_mall",
            "department_store",
            "supermarket",
        ]
        raw_places = self._search_nearby(
            lat,
            lon,
            radius_m,
            included_types=types,
            max_results=limit * 2,
        )
        places = self._to_places(lat, lon, raw_places)
        return dedup_and_cut(places, limit)

    def list_spots(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        limit: int = 10,
    ) -> list[GPlace]:
        limit = max(0, int(limit))
        if limit == 0:
            return []

        nearby_types = ["park", "tourist_attraction"]
        r1 = self._search_nearby(lat, lon, radius_m, nearby_types, limit)
        r2 = self._search_text(
            lat,
            lon,
            radius_m,
            "belvédère",
            max_results=limit,
        )
        r3 = self._search_text(
            lat,
            lon,
            radius_m,
            "rooftop panorama",
            max_results=limit,
        )
        r4 = self._search_text(
            lat,
            lon,
            radius_m,
            "plage beach",
            max_results=limit,
        )
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
        limit = max(0, int(limit))
        if limit == 0:
            return []

        nearby_types = [
            "museum",
            "art_gallery",
            "church",
            "zoo",
            "amusement_park",
            "botanical_garden",
        ]
        r1 = self._search_nearby(lat, lon, radius_m, nearby_types, limit)
        r2 = self._search_text(
            lat,
            lon,
            radius_m,
            "cathédrale",
            max_results=limit,
        )
        r3 = self._search_text(
            lat,
            lon,
            radius_m,
            "palais",
            max_results=limit,
        )
        r4 = self._search_text(
            lat,
            lon,
            radius_m,
            "château",
            max_results=limit,
        )
        places = (
            self._to_places(lat, lon, r1)
            + self._to_places(lat, lon, r2)
            + self._to_places(lat, lon, r3)
            + self._to_places(lat, lon, r4)
        )
        return dedup_and_cut(places, limit)


__all__ = ["GPlace", "GooglePlacesService", "dedup_and_cut", "GooglePlacesError"]
