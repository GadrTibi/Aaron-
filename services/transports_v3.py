"""Transport service aggregating GTFS, OSM Overpass and Google Places."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
from zipfile import ZipFile

import requests

from app.services.overpass_client import query_overpass
from app.views.settings_keys import read_local_secret
from services.transport_cache import TransportCache


@dataclass
class TransportResult:
    metro_lines: list[str]
    bus_lines: list[str]
    taxis: list[str]
    provider_used: dict[str, str]
    cache_status: str | None = None


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance between two points on Earth in meters."""

    rad = math.radians
    dlat = rad(lat2 - lat1)
    dlon = rad(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371000 * c


class GTFSProvider:
    """Read local GTFS archives to extract transport lines."""

    METRO_TYPES = {0, 1, 2}
    BUS_TYPES = {3}

    def __init__(self, base_dir: str | Path = "data/gtfs") -> None:
        self.base_dir = Path(base_dir)

    def _iter_archives(self, city: Optional[str]) -> Iterable[Path]:
        if not self.base_dir.exists():
            return []
        if city:
            candidate = self.base_dir / f"{city}.zip"
            if candidate.exists():
                return [candidate]
        return sorted(self.base_dir.glob("*.zip"))

    def _read_csv(self, zf: ZipFile, name: str) -> Iterable[dict[str, str]]:
        try:
            with zf.open(name) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
                yield from csv.DictReader(text)
        except KeyError:
            return []

    @staticmethod
    def _to_float(value: str | None) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_lines(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        city: Optional[str] = None,
    ) -> tuple[list[str], list[str]]:
        metro_candidates: list[tuple[float, str]] = []
        bus_candidates: list[tuple[float, str]] = []

        archives = list(self._iter_archives(city))
        if not archives:
            return [], []

        for archive in archives:
            try:
                zf = ZipFile(archive)
            except (FileNotFoundError, OSError):
                continue
            with zf:
                stops: Dict[str, float] = {}
                for row in self._read_csv(zf, "stops.txt"):
                    stop_id = row.get("stop_id")
                    lat_val = self._to_float(row.get("stop_lat"))
                    lon_val = self._to_float(row.get("stop_lon"))
                    if not stop_id or lat_val is None or lon_val is None:
                        continue
                    distance = _haversine_distance_m(lat, lon, lat_val, lon_val)
                    if distance <= radius_m:
                        stops[stop_id] = distance
                if not stops:
                    continue

                trips_by_stop: Dict[str, set[str]] = {sid: set() for sid in stops}
                all_trip_ids: set[str] = set()
                for row in self._read_csv(zf, "stop_times.txt"):
                    stop_id = row.get("stop_id")
                    trip_id = row.get("trip_id")
                    if not stop_id or stop_id not in trips_by_stop or not trip_id:
                        continue
                    trips_by_stop[stop_id].add(trip_id)
                    all_trip_ids.add(trip_id)
                if not all_trip_ids:
                    continue

                trip_to_route: Dict[str, str] = {}
                for row in self._read_csv(zf, "trips.txt"):
                    trip_id = row.get("trip_id")
                    route_id = row.get("route_id")
                    if trip_id in all_trip_ids and route_id:
                        trip_to_route[trip_id] = route_id
                if not trip_to_route:
                    continue

                route_ids: set[str] = set(trip_to_route.values())
                route_info: Dict[str, tuple[str, Optional[int]]] = {}
                for row in self._read_csv(zf, "routes.txt"):
                    route_id = row.get("route_id")
                    if not route_id or route_id not in route_ids:
                        continue
                    short_name = (row.get("route_short_name") or "").strip()
                    long_name = (row.get("route_long_name") or "").strip()
                    label = short_name or long_name or route_id
                    try:
                        route_type = int(row.get("route_type", ""))
                    except (TypeError, ValueError):
                        route_type = None
                    route_info[route_id] = (label, route_type)
                if not route_info:
                    continue

                for stop_id, distance in sorted(stops.items(), key=lambda x: x[1]):
                    trip_ids = trips_by_stop.get(stop_id)
                    if not trip_ids:
                        continue
                    seen_route_ids = set()
                    for trip_id in trip_ids:
                        route_id = trip_to_route.get(trip_id)
                        if not route_id or route_id in seen_route_ids:
                            continue
                        seen_route_ids.add(route_id)
                        label, route_type = route_info.get(route_id, (None, None))
                        if not label:
                            continue
                        label_text = str(label).strip()
                        if not label_text:
                            continue
                        if route_type in self.METRO_TYPES:
                            metro_candidates.append((distance, label_text))
                        elif route_type in self.BUS_TYPES:
                            bus_candidates.append((distance, label_text))
                if len(metro_candidates) >= 3 and len(bus_candidates) >= 3:
                    break

        metro_lines = self._dedupe_sorted(metro_candidates)
        bus_lines = self._dedupe_sorted(bus_candidates)
        return metro_lines, bus_lines

    @staticmethod
    def _dedupe_sorted(candidates: Iterable[tuple[float, str]]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for _, label in sorted(candidates, key=lambda x: x[0]):
            norm = str(label).strip()
            if not norm or norm.lower() in seen:
                continue
            seen.add(norm.lower())
            result.append(norm)
            if len(result) >= 3:
                break
        return result

    def get_metro_lines(
        self, lat: float, lon: float, radius_m: int, city: Optional[str] = None
    ) -> list[str]:
        metro, _ = self._extract_lines(lat, lon, radius_m, city)
        return metro

    def get_bus_lines(
        self, lat: float, lon: float, radius_m: int, city: Optional[str] = None
    ) -> list[str]:
        _, bus = self._extract_lines(lat, lon, radius_m, city)
        return bus

    def get_taxis(self, lat: float, lon: float, radius_m: int, city: Optional[str] = None) -> list[str]:
        return []


class OSMProvider:
    """Fetch transport information from OSM Overpass API."""

    def _execute(self, query: str, label: str) -> list[dict]:
        elements, _ = query_overpass(query, label)
        return elements

    @staticmethod
    def _unique(items: Iterable[str], limit: int) -> list[str]:
        seen: set[str] = set()
        results: list[str] = []
        for item in items:
            value = item.strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(value)
            if len(results) >= limit:
                break
        return results

    def get_metro_lines(self, lat: float, lon: float, radius_m: int) -> list[str]:
        query = (
            "[out:json][timeout:25];\n"
            "(\n"
            f"  nwr(around:{radius_m},{lat},{lon})[railway=station][station=subway];\n"
            ");\n"
            "out tags 80;"
        )
        elements = self._execute(query, "metro_subway")
        names = [el.get("tags", {}).get("name", "") for el in elements]
        return self._unique(names, 3)

    def get_bus_lines(self, lat: float, lon: float, radius_m: int) -> list[str]:
        query = (
            "[out:json][timeout:25];\n"
            "(\n"
            f"  node(around:{radius_m},{lat},{lon})[highway=bus_stop];\n"
            ");\n"
            "out tags 120;"
        )
        elements = self._execute(query, "bus_stops")
        refs: list[str] = []
        for el in elements:
            tags = el.get("tags", {})
            raw_ref = tags.get("ref") or ""
            if raw_ref:
                parts = [part.strip() for part in raw_ref.replace(",", ";").split(";")]
                refs.extend([part for part in parts if part])
            else:
                name = tags.get("name")
                if name:
                    refs.append(name)
        return self._unique(refs, 3)

    def get_taxis(self, lat: float, lon: float, radius_m: int) -> list[str]:
        query = (
            "[out:json][timeout:25];\n"
            "(\n"
            f"  nwr(around:{radius_m},{lat},{lon})[amenity=taxi];\n"
            ");\n"
            "out tags 50;"
        )
        elements = self._execute(query, "taxi_stands")
        names = [el.get("tags", {}).get("name", "") for el in elements]
        return self._unique(names, 3)


class GoogleProvider:
    """Fallback provider relying on Google Places Nearby Search."""

    ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or read_local_secret("GOOGLE_MAPS_API_KEY")

    def _search(self, lat: float, lon: float, radius_m: int, included: list[str], limit: int) -> list[str]:
        if not self.api_key:
            return []
        payload = {
            "includedTypes": included,
            "maxResultCount": min(limit, 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": radius_m,
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "places.displayName",
        }
        try:
            response = requests.post(self.ENDPOINT, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            return []
        data = response.json()
        places = data.get("places", []) if isinstance(data, dict) else []
        names: list[str] = []
        for place in places:
            display = place.get("displayName")
            if isinstance(display, dict):
                name = display.get("text")
            else:
                name = None
            if not name:
                name = place.get("name")
            if name:
                names.append(str(name))
        unique: list[str] = []
        seen: set[str] = set()
        for name in names:
            norm = name.strip()
            if not norm:
                continue
            key = norm.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(norm)
            if len(unique) >= limit:
                break
        return unique

    def get_metro_lines(self, lat: float, lon: float, radius_m: int) -> list[str]:
        return self._search(lat, lon, radius_m, ["subway_station"], 3)

    def get_bus_lines(self, lat: float, lon: float, radius_m: int) -> list[str]:
        return self._search(lat, lon, radius_m, ["bus_station"], 3)

    def get_taxis(self, lat: float, lon: float, radius_m: int) -> list[str]:
        return self._search(lat, lon, radius_m, ["taxi_stand"], 3)


class TransportService:
    """Aggregate transport data from multiple providers."""

    def __init__(self, provider_order: tuple[str, ...] = ("gtfs", "osm", "google"), *, cache: TransportCache | None = None) -> None:
        self.provider_order = list(provider_order)
        self.providers: dict[str, object] = {}
        self.cache = cache or TransportCache()
        for name in {"gtfs", "osm", "google"}:
            if name == "gtfs":
                self.providers[name] = GTFSProvider()
            elif name == "osm":
                self.providers[name] = OSMProvider()
            elif name == "google":
                self.providers[name] = GoogleProvider()

    def _get_provider(self, name: str) -> Optional[object]:
        return self.providers.get(name)

    def _try_providers(self, providers: Iterable[str], mode: str, lat: float, lon: float, radius_m: int) -> tuple[list[str], Optional[str]]:
        method_name = {
            "metro": "get_metro_lines",
            "bus": "get_bus_lines",
            "taxi": "get_taxis",
        }[mode]
        for provider_name in providers:
            provider = self._get_provider(provider_name)
            if provider is None:
                continue
            getter = getattr(provider, method_name, None)
            if not getter:
                continue
            try:
                lines = getter(lat, lon, radius_m)
            except Exception:
                continue
            cleaned = self._normalize_lines(lines, limit=3 if mode != "taxi" else 3)
            if cleaned:
                return cleaned, provider_name
        return [], None

    @staticmethod
    def _normalize_lines(lines: Iterable[str], limit: int) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for line in lines:
            if not line:
                continue
            text = str(line).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    def get(self, lat: float, lon: float, radius_m: int = 1200, *, use_cache: bool = True) -> TransportResult:
        metro_order = [name for name in self.provider_order if name in {"gtfs", "osm", "google"}]
        if not metro_order:
            metro_order = ["gtfs", "osm", "google"]
        bus_order = metro_order
        taxi_order = ["osm", "google"]

        if use_cache and self.cache:
            cached = self.cache.get(lat, lon, radius_m, metro_order)
            if cached:
                payload = cached or {}
                return TransportResult(
                    metro_lines=list(payload.get("metro_lines", [])),
                    bus_lines=list(payload.get("bus_lines", [])),
                    taxis=list(payload.get("taxis", [])),
                    provider_used=dict(payload.get("provider_used", {})),
                    cache_status="hit",
                )

        metro_lines, metro_provider = self._try_providers(metro_order, "metro", lat, lon, radius_m)
        bus_lines, bus_provider = self._try_providers(bus_order, "bus", lat, lon, radius_m)
        taxis, taxi_provider = self._try_providers(taxi_order, "taxi", lat, lon, radius_m)

        provider_used = {}
        if metro_provider:
            provider_used["metro"] = metro_provider
        if bus_provider:
            provider_used["bus"] = bus_provider
        if taxi_provider:
            provider_used["taxi"] = taxi_provider

        result = {
            "metro_lines": metro_lines,
            "bus_lines": bus_lines,
            "taxis": taxis,
            "provider_used": provider_used,
        }
        if use_cache and self.cache:
            self.cache.set(lat, lon, radius_m, metro_order, result)

        return TransportResult(
            metro_lines=metro_lines,
            bus_lines=bus_lines,
            taxis=taxis,
            provider_used=provider_used,
            cache_status="miss",
        )


__all__ = ["TransportResult", "TransportService"]
