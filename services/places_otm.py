from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import requests

from config import places_settings

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Visit:
    name: str
    lat: float
    lon: float
    distance_m: float
    kinds: List[str]
    raw: Dict[str, Any]


class OpenTripMapService:
    """Client for the OpenTripMap API."""

    BASE_URL = "https://api.opentripmap.com/0.1"
    CACHE_TTL_SECONDS = 48 * 3600
    _KIND_FILTERS = [
        "museums",
        "historic_architecture",
        "palaces",
        "castles",
        "theatres",
        "opera",
        "temples",
        "cathedrals",
        "botanical_gardens",
        "zoos",
        "theme_parks",
        "art_galleries",
    ]

    def __init__(self, api_key: str | None = None, lang: str = "fr") -> None:
        key = api_key if api_key is not None else places_settings.OPENTRIPMAP_API_KEY
        if not key:
            raise ValueError("OPENTRIPMAP_API_KEY manquant")
        self.api_key = key
        self.lang = lang
        self._session = requests.Session()
        self._session.headers.update(places_settings.build_headers())

    def list_visits(
        self, lat: float, lon: float, radius_m: int, limit: int = 10
    ) -> List[Visit]:
        cache_key = f"otm:visits:{round(lat, 5)}:{round(lon, 5)}:{radius_m}:{limit}:{self.lang}"
        cached = places_settings.read_cache_json(cache_key, self.CACHE_TTL_SECONDS)
        if cached:
            return [Visit(**entry) for entry in cached]

        try:
            visits = self._fetch_visits(lat, lon, radius_m, limit)
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning("OpenTripMap failure: %s", exc)
            return []

        if visits:
            places_settings.write_cache_json(cache_key, [asdict(visit) for visit in visits])
        return visits

    def _fetch_visits(self, lat: float, lon: float, radius_m: int, limit: int) -> List[Visit]:
        radius_url = f"{self.BASE_URL}/{self.lang}/places/radius"
        params = {
            "radius": radius_m,
            "lon": lon,
            "lat": lat,
            "kinds": ",".join(self._KIND_FILTERS),
            "limit": 100,
            "apikey": self.api_key,
        }
        payload = self._request_json(radius_url, params)
        if payload is None:
            return []

        features = payload.get("features", [])
        collected: List[Visit] = []
        seen: set[str] = set()
        for feature in features:
            properties: Dict[str, Any] = feature.get("properties", {})
            geometry: Dict[str, Any] = feature.get("geometry", {})
            coordinates = geometry.get("coordinates") or [None, None]
            lon2, lat2 = coordinates[0], coordinates[1]
            xid = properties.get("xid")
            if not xid:
                continue
            if xid in seen:
                continue
            seen.add(xid)

            name = properties.get("name") or ""
            kinds_list = self._parse_kinds(properties.get("kinds"))
            raw_detail: Dict[str, Any] | None = None

            if (not name or not kinds_list or lat2 is None or lon2 is None) and xid:
                detail = self._fetch_detail(xid)
                if detail:
                    raw_detail = detail
                    name = detail.get("name") or name
                    point = detail.get("point", {})
                    lat2 = lat2 if lat2 is not None else point.get("lat")
                    lon2 = lon2 if lon2 is not None else point.get("lon")
                    if not kinds_list:
                        kinds_list = self._parse_kinds(detail.get("kinds"))

            if lat2 is None or lon2 is None:
                continue

            distance = self._compute_distance(
                lat, lon, float(lat2), float(lon2), properties.get("dist")
            )
            collected.append(
                Visit(
                    name=name or "Lieu",
                    lat=float(lat2),
                    lon=float(lon2),
                    distance_m=distance,
                    kinds=kinds_list,
                    raw={"feature": feature, "detail": raw_detail} if raw_detail else feature,
                )
            )

            if len(collected) >= limit:
                break

        collected.sort(key=lambda visit: visit.distance_m)
        return collected[:limit]

    def _fetch_detail(self, xid: str) -> Dict[str, Any] | None:
        url = f"{self.BASE_URL}/{self.lang}/places/xid/{xid}"
        return self._request_json(url, {"apikey": self.api_key})

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
                    LOGGER.warning("OpenTripMap request failed after retries: %s", exc)
                    return None
                self._sleep_with_backoff(attempt)

    def _sleep_with_backoff(self, attempt: int) -> None:
        delay = places_settings.RETRY_BASE_DELAY * (2 ** (attempt - 1))
        delay += random.uniform(0, places_settings.RETRY_JITTER)
        time.sleep(delay)

    @staticmethod
    def _parse_kinds(raw_kinds: Any) -> List[str]:
        if isinstance(raw_kinds, str):
            return [kind for kind in (segment.strip() for segment in raw_kinds.split(",")) if kind]
        if isinstance(raw_kinds, list):
            return [str(kind) for kind in raw_kinds]
        return []

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
