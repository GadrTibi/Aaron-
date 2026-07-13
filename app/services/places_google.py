from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import requests


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


def _post_json(
    url: str,
    headers: dict,
    payload: dict,
    timeout: int = 10,
    retries: int = 2,
    backoff: float = 0.6,
    jitter: float = 0.2,
    post: Callable[..., requests.Response] | None = None,
):
    last = None
    post_func = post or requests.post
    for attempt in range(retries + 1):
        r = post_func(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
                msg = err.get("message") or r.text[:300]
            except Exception:
                msg = r.text[:300]
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                delay = backoff * (2 ** attempt)
                delay += delay * random.uniform(-jitter, jitter)
                time.sleep(max(0.2, delay))
                continue
            raise RuntimeError(f"Google Places error {r.status_code}: {msg}")
        try:
            return r.json()
        except Exception as e:
            last = e
    raise RuntimeError(f"Google Places: invalid JSON response ({last})")


def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    from math import radians, sin, cos, sqrt, atan2

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _to_place(item: dict, origin_lat: float, origin_lon: float) -> dict:
    name = item.get("displayName", {}).get("text") or ""
    loc = item.get("location", {})
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    dist = _haversine_m(origin_lat, origin_lon, lat, lon) if (lat is not None and lon is not None) else 0.0
    return {
        "id": item.get("id"),
        "name": name,
        "lat": lat,
        "lon": lon,
        "types": item.get("types", []) or [],
        "distance_m": dist,
        "raw": item,
    }


def _dedup_and_sort(items: list[dict], limit: int) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        pid = it.get("id")
        key = pid or f"{it.get('name','')}:{round(it.get('lat',0),5)}:{round(it.get('lon',0),5)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    out.sort(key=lambda x: x.get("distance_m", 1e12))
    return out[:limit]


def dedup_and_cut(items: Iterable[GPlace], limit: int) -> list[GPlace]:
    mapped: list[dict] = []
    for place in items:
        mapped.append(
            {
                "id": place.place_id or None,
                "name": place.name,
                "lat": place.lat,
                "lon": place.lon,
                "types": place.types,
                "distance_m": place.distance_m,
                "raw": place.raw,
            }
        )
    deduped = _dedup_and_sort(mapped, limit)
    result: list[GPlace] = []
    for entry in deduped:
        lat = entry.get("lat")
        lon = entry.get("lon")
        if lat is None or lon is None:
            continue
        name = entry.get("name") or entry.get("id") or "Sans nom"
        result.append(
            GPlace(
                name=name,
                place_id=str(entry.get("id") or ""),
                lat=float(lat),
                lon=float(lon),
                distance_m=float(entry.get("distance_m", 0.0)),
                types=list(entry.get("types", []) or []),
                raw=entry.get("raw", {}),
            )
        )
    return result


class GooglePlacesService:
    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        if not api_key:
            raise ValueError("Google Places API key is required")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _headers(self) -> dict:
        return {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
            "Content-Type": "application/json",
        }

    def _post(self, url: str, payload: dict) -> dict:
        return _post_json(url, self._headers(), payload, post=self.session.post)

    def _search_nearby(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        included_types: list[str],
        max_results: int,
    ) -> list[dict]:
        types = [t for t in included_types if isinstance(t, str)]
        types = [t.strip() for t in types if t.strip()]
        types = [t for t in types if t in ALLOWED_TYPES_NEARBY]
        if not types:
            raise ValueError("No valid includedTypes for Nearby")

        url = f"{BASE}/places:searchNearby"
        remaining = max(0, int(max_results))
        results: list[dict] = []
        for t in dict.fromkeys(types):
            if remaining <= 0:
                break
            payload = {
                "includedTypes": [t],
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lon},
                        "radius": float(radius_m),
                    }
                },
                "maxResultCount": min(MAX_PER_CALL, remaining),
                "languageCode": "fr",
            }
            data = self._post(url, payload)
            results.extend(data.get("places", []) if isinstance(data, dict) else [])
            remaining = max(0, remaining - MAX_PER_CALL)
        return results

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

        url = f"{BASE}/places:searchText"
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
        data = self._post(url, payload)
        return data.get("places", []) if isinstance(data, dict) else []

    @staticmethod
    def _map_results(lat: float, lon: float, places: Iterable[dict], limit: int) -> list[GPlace]:
        mapped = [_to_place(p, lat, lon) for p in places if isinstance(p, dict)]
        deduped = _dedup_and_sort(mapped, limit)
        result: list[GPlace] = []
        for item in deduped:
            lat_val = item.get("lat")
            lon_val = item.get("lon")
            if lat_val is None or lon_val is None:
                continue
            name = item.get("name") or item.get("id") or "Sans nom"
            result.append(
                GPlace(
                    name=name,
                    place_id=str(item.get("id") or ""),
                    lat=float(lat_val),
                    lon=float(lon_val),
                    distance_m=float(item.get("distance_m", 0.0)),
                    types=list(item.get("types", []) or []),
                    raw=item.get("raw", {}),
                )
            )
        return result

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
        return self._map_results(lat, lon, raw_places, limit)

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
        raw = r1 + r2 + r3 + r4
        return self._map_results(lat, lon, raw, limit)

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
        raw = r1 + r2 + r3 + r4
        return self._map_results(lat, lon, raw, limit)


__all__ = ["GPlace", "GooglePlacesService", "dedup_and_cut"]
