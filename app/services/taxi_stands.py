from __future__ import annotations

import math
from typing import Iterable, Optional

import requests

from app.services.provider_status import resolve_api_key


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.radians
    dlat = rad(lat2 - lat1)
    dlon = rad(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371000 * c


def _request_places(lat: float, lon: float, radius_m: int, api_key: str, timeout: int = 7, session: Optional[requests.Session] = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.location",
    }
    payload = {
        "includedTypes": ["taxi_stand"],
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": float(radius_m),
            }
        },
        "maxResultCount": 8,
    }
    post = session.post if session else requests.post
    resp = post("https://places.googleapis.com/v1/places:searchNearby", headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _to_stand(item: dict, origin_lat: float, origin_lon: float) -> dict:
    display = item.get("displayName") or {}
    name = display.get("text") if isinstance(display, dict) else None
    loc = item.get("location") or {}
    lat = loc.get("latitude")
    lon = loc.get("longitude")
    if lat is None or lon is None:
        return {}
    distance_m = _haversine_m(origin_lat, origin_lon, float(lat), float(lon))
    return {"name": name or "Station de taxis", "distance_m": distance_m}


def _parse_response(data: dict, origin_lat: float, origin_lon: float) -> list[dict]:
    places = data.get("places") if isinstance(data, dict) else []
    stands: list[dict] = []
    for place in places or []:
        entry = _to_stand(place, origin_lat, origin_lon)
        if entry:
            stands.append(entry)
    stands.sort(key=lambda s: s.get("distance_m", float("inf")))
    return stands[:2]


def find_nearby_taxi_stands(
    lat: float,
    lon: float,
    radius_m: int = 300,
    api_key: str | None = None,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    if api_key is None:
        api_key, _ = resolve_api_key("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return []
    try:
        data = _request_places(lat, lon, radius_m, api_key, session=session)
    except requests.Timeout:
        return []
    except requests.RequestException:
        return []
    return _parse_response(data, lat, lon)


def build_taxi_lines_from_stands(stands: Iterable[dict]) -> str:
    lines: list[str] = []
    for stand in stands:
        name = stand.get("name") or "Station de taxis"
        distance = stand.get("distance_m") or 0
        try:
            minutes = max(1, round(float(distance) / 80.0))
        except Exception:
            minutes = 2
        lines.append(f"Station de taxis {name} ({int(minutes)} min à pied)")
        if len(lines) >= 2:
            break
    return "\n".join(lines)
