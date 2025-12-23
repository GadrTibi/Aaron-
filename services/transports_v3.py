"""Transport service aggregating GTFS, OSM Overpass and Google Places."""

from __future__ import annotations

import csv
import io
import math
import time
import weakref
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, TimeoutError, wait, Future
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Sequence
from zipfile import ZipFile

import requests

from app.services.overpass_client import query_overpass
from app.views.settings_keys import read_local_secret

try:  # Streamlit may not be available in test environments
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    st = None


FAST_MODE = True
TARGET_COUNT = 3
BUDGET_GTFS_S = 0.25
BUDGET_OSM_S = 1.80
BUDGET_GMAPS_S = 1.80
SHOW_DEBUG = False

DEFAULT_GTFS_BASE_DIR = Path("data/gtfs")
_SERVICE_REGISTRY: "weakref.WeakValueDictionary[int, TransportService]" = weakref.WeakValueDictionary()


@dataclass
class TransportResult:
    metro_lines: list[str]
    bus_lines: list[str]
    taxis: list[str]
    provider_used: dict[str, str]


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


class GTFSIndex:
    """In-memory index extracted from a GTFS archive."""

    def __init__(
        self,
        stops: dict[str, tuple[float, float, str]],
        stop_routes: dict[str, set[str]],
        routes: dict[str, tuple[str, Optional[int]]],
    ) -> None:
        self.stops = stops
        self.stop_routes = stop_routes
        self.routes = routes
        self._stops_list: list[tuple[str, float, float, str]] = [
            (stop_id, lat, lon, name) for stop_id, (lat, lon, name) in stops.items()
        ]

    def routes_near(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        route_types: set[int],
        target: int,
    ) -> list[str]:
        if not self._stops_list or target <= 0:
            return []

        candidates: list[tuple[float, str]] = []
        for stop_id, stop_lat, stop_lon, _ in self._stops_list:
            distance = _haversine_distance_m(lat, lon, stop_lat, stop_lon)
            if distance > radius_m:
                continue
            route_ids = self.stop_routes.get(stop_id)
            if not route_ids:
                continue
            for route_id in route_ids:
                label, route_type = self.routes.get(route_id, ("", None))
                if route_type is None or route_type not in route_types:
                    continue
                text = label.strip()
                if not text:
                    continue
                candidates.append((distance, text))

        if not candidates:
            return []

        candidates.sort(key=lambda item: item[0])
        seen: set[str] = set()
        results: list[str] = []
        for _, label in candidates:
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(label)
            if len(results) >= target:
                break
        return results


def _gtfs_to_float(value: str | None) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=8)
def load_gtfs_index(city: str) -> Optional[GTFSIndex]:
    archive = DEFAULT_GTFS_BASE_DIR / f"{city}.zip"
    if not archive.exists():
        return None
    try:
        zf = ZipFile(archive)
    except (FileNotFoundError, OSError):
        return None

    stops: dict[str, tuple[float, float, str]] = {}
    stop_routes: dict[str, set[str]] = {}
    trip_to_route: dict[str, str] = {}
    routes: dict[str, tuple[str, Optional[int]]] = {}

    with zf:
        try:
            with zf.open("stops.txt") as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
                for row in reader:
                    stop_id = row.get("stop_id")
                    lat_val = _gtfs_to_float(row.get("stop_lat"))
                    lon_val = _gtfs_to_float(row.get("stop_lon"))
                    if not stop_id or lat_val is None or lon_val is None:
                        continue
                    name = (row.get("stop_name") or "").strip()
                    stops[stop_id] = (lat_val, lon_val, name)
                    stop_routes[stop_id] = set()
        except KeyError:
            return None

        try:
            with zf.open("trips.txt") as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
                for row in reader:
                    trip_id = row.get("trip_id")
                    route_id = row.get("route_id")
                    if trip_id and route_id:
                        trip_to_route[trip_id] = route_id
        except KeyError:
            trip_to_route = {}

        try:
            with zf.open("stop_times.txt") as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
                for row in reader:
                    stop_id = row.get("stop_id")
                    trip_id = row.get("trip_id")
                    if not stop_id or stop_id not in stop_routes or not trip_id:
                        continue
                    route_id = trip_to_route.get(trip_id)
                    if route_id:
                        stop_routes[stop_id].add(route_id)
        except KeyError:
            stop_routes = {sid: routes for sid, routes in stop_routes.items() if routes}

        try:
            with zf.open("routes.txt") as fh:
                reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
                for row in reader:
                    route_id = row.get("route_id")
                    if not route_id:
                        continue
                    short_name = (row.get("route_short_name") or "").strip()
                    long_name = (row.get("route_long_name") or "").strip()
                    label = short_name or long_name or route_id
                    try:
                        route_type = int(row.get("route_type", ""))
                    except (TypeError, ValueError):
                        route_type = None
                    routes[route_id] = (label, route_type)
        except KeyError:
            routes = {}

    return GTFSIndex(stops, stop_routes, routes)


class GTFSProvider:
    """Read local GTFS archives to extract transport lines."""

    METRO_TYPES = {0, 1, 2}
    BUS_TYPES = {3}

    def __init__(self, base_dir: str | Path = "data/gtfs") -> None:
        self.base_dir = Path(base_dir)
        global DEFAULT_GTFS_BASE_DIR
        DEFAULT_GTFS_BASE_DIR = self.base_dir

    def _iter_archives(self, city: Optional[str]) -> Iterable[Path]:
        if not self.base_dir.exists():
            return []
        if city:
            candidate = self.base_dir / f"{city}.zip"
            if candidate.exists():
                return [candidate]
        return sorted(self.base_dir.glob("*.zip"))

    def _routes_from_archives(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        route_types: set[int],
        target: int,
        city: Optional[str] = None,
    ) -> list[str]:
        archives = list(self._iter_archives(city))
        if not archives:
            return []

        collected: list[str] = []
        seen: set[str] = set()
        for archive in archives:
            index = load_gtfs_index(archive.stem)
            if not index:
                continue
            lines = index.routes_near(lat, lon, radius_m, route_types, target)
            for line in lines:
                key = line.lower()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(line)
                if len(collected) >= target:
                    return collected[:target]
        return collected[:target]

    def get_metro_lines(
        self, lat: float, lon: float, radius_m: int, city: Optional[str] = None
    ) -> list[str]:
        return self._routes_from_archives(
            lat, lon, radius_m, self.METRO_TYPES, TARGET_COUNT, city
        )

    def get_bus_lines(
        self, lat: float, lon: float, radius_m: int, city: Optional[str] = None
    ) -> list[str]:
        return self._routes_from_archives(
            lat, lon, radius_m, self.BUS_TYPES, TARGET_COUNT, city
        )

    def get_taxis(self, lat: float, lon: float, radius_m: int, city: Optional[str] = None) -> list[str]:
        return []


class OSMProvider:
    """Fetch transport information from OSM Overpass API."""

    METRO_MAX_RADIUS = 1500
    BUS_MAX_RADIUS = 1000
    TAXI_MAX_RADIUS = 1200

    def _execute(self, query: str, label: str, fallback: Optional[str] = None) -> list[dict]:
        try:
            elements, _ = query_overpass(query, label)
            return elements
        except Exception:
            if fallback is None:
                raise
            elements, _ = query_overpass(fallback, f"{label}_fallback")
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
        radius = min(radius_m, self.METRO_MAX_RADIUS)
        node_query = (
            "[out:json][timeout:12];\n"
            f"node(around:{radius},{lat},{lon})[railway=station][station=subway];\n"
            "out tags 50;"
        )
        fallback_query = (
            "[out:json][timeout:12];\n"
            "(\n"
            f"  nwr(around:{radius},{lat},{lon})[railway=station][station=subway];\n"
            ");\n"
            "out tags 50;"
        )
        try:
            elements = self._execute(node_query, "metro_subway", fallback_query)
        except Exception:
            return []
        names: list[str] = []
        for el in elements:
            name = el.get("tags", {}).get("name") or ""
            if name:
                names.append(name)
            if len(names) >= TARGET_COUNT:
                break
        return self._unique(names, TARGET_COUNT)

    def get_bus_lines(self, lat: float, lon: float, radius_m: int) -> list[str]:
        radius = min(radius_m, self.BUS_MAX_RADIUS)
        node_query = (
            "[out:json][timeout:12];\n"
            f"node(around:{radius},{lat},{lon})[highway=bus_stop];\n"
            "out tags 80;"
        )
        try:
            elements = self._execute(node_query, "bus_stops")
        except Exception:
            return []
        refs: list[str] = []
        for el in elements:
            tags = el.get("tags", {})
            raw_ref = tags.get("ref") or ""
            if raw_ref:
                parts = [part.strip() for part in raw_ref.replace(",", ";").split(";")]
                for part in parts:
                    if not part:
                        continue
                    refs.append(part)
                    if len(refs) >= TARGET_COUNT:
                        break
            if len(refs) >= TARGET_COUNT:
                break
            name = tags.get("name")
            if name:
                refs.append(name)
                if len(refs) >= TARGET_COUNT:
                    break
        return self._unique(refs, TARGET_COUNT)

    def get_taxis(self, lat: float, lon: float, radius_m: int) -> list[str]:
        radius = min(radius_m, self.TAXI_MAX_RADIUS)
        node_query = (
            "[out:json][timeout:12];\n"
            f"node(around:{radius},{lat},{lon})[amenity=taxi];\n"
            "out tags 50;"
        )
        fallback_query = (
            "[out:json][timeout:12];\n"
            "(\n"
            f"  nwr(around:{radius},{lat},{lon})[amenity=taxi];\n"
            ");\n"
            "out tags 50;"
        )
        try:
            elements = self._execute(node_query, "taxi_stands", fallback_query)
        except Exception:
            return []
        names: list[str] = []
        for el in elements:
            name = el.get("tags", {}).get("name") or ""
            if name:
                names.append(name)
            if len(names) >= TARGET_COUNT:
                break
        return self._unique(names, TARGET_COUNT)


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
            "maxResultCount": min(limit, 5),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lon},
                    "radius": min(radius_m, 1500),
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "places.displayName",
        }
        try:
            response = requests.post(self.ENDPOINT, json=payload, headers=headers, timeout=10)
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

    _MODE_METHODS = {
        "metro": "get_metro_lines",
        "bus": "get_bus_lines",
        "taxi": "get_taxis",
    }

    def __init__(self, provider_order: tuple[str, ...] = ("gtfs", "osm", "google")) -> None:
        self.provider_order = list(provider_order)
        self.providers: dict[str, object] = {}
        for name in {"gtfs", "osm", "google"}:
            if name == "gtfs":
                self.providers[name] = GTFSProvider()
            elif name == "osm":
                self.providers[name] = OSMProvider()
            elif name == "google":
                self.providers[name] = GoogleProvider()
        _SERVICE_REGISTRY[id(self)] = self

    def _get_provider(self, name: str) -> Optional[object]:
        return self.providers.get(name)

    @staticmethod
    def _normalize_lines(lines: Iterable[str], limit: int = TARGET_COUNT) -> list[str]:
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

    def _providers_for_mode(self, mode: str) -> list[str]:
        allowed = {
            "metro": ["gtfs", "osm", "google"],
            "bus": ["gtfs", "osm", "google"],
            "taxi": ["osm", "google"],
        }[mode]
        providers: list[str] = []
        for name in self.provider_order:
            if name in allowed and name not in providers:
                providers.append(name)
        for name in allowed:
            if name not in providers:
                providers.append(name)
        return providers

    @staticmethod
    def _radius_for_provider(mode: str, provider: str, radius_m: int) -> int:
        if provider == "osm":
            if mode == "metro":
                return min(radius_m, OSMProvider.METRO_MAX_RADIUS)
            if mode == "bus":
                return min(radius_m, OSMProvider.BUS_MAX_RADIUS)
            if mode == "taxi":
                return min(radius_m, OSMProvider.TAXI_MAX_RADIUS)
        if provider == "google":
            return min(radius_m, 1500)
        return radius_m

    def _call_provider(
        self,
        getter,
        lat: float,
        lon: float,
        radius_m: int,
    ) -> tuple[list[str], float]:
        start = time.perf_counter()
        try:
            lines = getter(lat, lon, radius_m)
        except Exception:
            lines = []
        duration = time.perf_counter() - start
        return self._normalize_lines(lines, TARGET_COUNT), duration

    def _consume_future(
        self,
        name: str,
        futures: dict[str, Future[tuple[list[str], float]]],
        durations: dict[str, float],
        results: dict[str, list[str]],
    ) -> list[str]:
        future = futures[name]
        try:
            lines, duration = future.result()
        except Exception:
            lines, duration = [], 0.0
        durations[name] += duration
        results[name] = lines
        return lines

    def _resolve_category(
        self,
        mode: str,
        lat: float,
        lon: float,
        radius_m: int,
        executor: ThreadPoolExecutor,
        durations: dict[str, float],
    ) -> tuple[list[str], Optional[str]]:
        providers = self._providers_for_mode(mode)
        method_name = self._MODE_METHODS[mode]
        futures: dict[str, Future[tuple[list[str], float]]] = {}
        future_to_name: dict[Future[tuple[list[str], float]], str] = {}
        start_times: dict[str, float] = {}

        for name in providers:
            provider = self._get_provider(name)
            if provider is None:
                continue
            getter = getattr(provider, method_name, None)
            if not getter:
                continue
            radius = self._radius_for_provider(mode, name, radius_m)
            future = executor.submit(self._call_provider, getter, lat, lon, radius)
            futures[name] = future
            future_to_name[future] = name
            start_times[name] = time.perf_counter()

        if not futures:
            return [], None

        budgets = {
            "gtfs": BUDGET_GTFS_S,
            "osm": BUDGET_OSM_S,
            "google": BUDGET_GMAPS_S,
        }
        deadlines = {
            name: start_times[name] + budgets.get(name, BUDGET_OSM_S)
            for name in futures
        }

        results: dict[str, list[str]] = {}
        best_provider: Optional[str] = None
        best_lines: list[str] = []
        pending = set(futures.keys())

        if "gtfs" in pending:
            try:
                lines, duration = futures["gtfs"].result(timeout=BUDGET_GTFS_S)
            except TimeoutError:
                pass
            except Exception:
                pending.remove("gtfs")
                durations["gtfs"] += 0.0
                results["gtfs"] = []
            else:
                durations["gtfs"] += duration
                lines = self._normalize_lines(lines, TARGET_COUNT)
                results["gtfs"] = lines
                pending.remove("gtfs")
                if len(lines) >= TARGET_COUNT:
                    best_provider = "gtfs"
                    best_lines = lines[:TARGET_COUNT]

        if best_provider:
            for name in pending:
                futures[name].cancel()
            return best_lines, best_provider

        while pending:
            now = time.perf_counter()
            ready = [name for name in list(pending) if futures[name].done()]
            for name in ready:
                lines = self._consume_future(name, futures, durations, results)
                pending.discard(name)
                if len(lines) >= TARGET_COUNT:
                    best_provider = name
                    best_lines = lines[:TARGET_COUNT]
                    break
            if best_provider or not pending:
                break

            next_deadline = min(deadlines[name] for name in pending)
            timeout = max(0.0, next_deadline - now)
            if timeout <= 0:
                expired = [name for name in list(pending) if deadlines[name] <= now]
                for name in expired:
                    futures[name].cancel()
                    pending.discard(name)
                continue

            done, _ = wait([futures[name] for name in pending], timeout=timeout, return_when=FIRST_COMPLETED)
            for future in done:
                name = future_to_name.get(future)
                if name is None or name not in pending:
                    continue
                lines = self._consume_future(name, futures, durations, results)
                pending.discard(name)
                if len(lines) >= TARGET_COUNT:
                    best_provider = name
                    best_lines = lines[:TARGET_COUNT]
                    break
            if best_provider:
                break

        if best_provider:
            for name in pending:
                futures[name].cancel()
            return best_lines, best_provider

        for name in pending:
            futures[name].cancel()

        best_lines = []
        best_provider = None
        for name in providers:
            lines = results.get(name)
            if not lines:
                continue
            if not best_lines or len(lines) > len(best_lines):
                best_lines = lines
                best_provider = name
            elif len(lines) == len(best_lines) and best_provider is not None:
                if providers.index(name) < providers.index(best_provider):
                    best_lines = lines
                    best_provider = name

        return best_lines[:TARGET_COUNT], best_provider

    def _compute(self, lat: float, lon: float, radius_m: int = 1200) -> TransportResult:
        start_total = time.perf_counter()
        durations = {"gtfs": 0.0, "osm": 0.0, "google": 0.0}

        if not FAST_MODE:
            return self._compute_sequential(lat, lon, radius_m, durations)

        with ThreadPoolExecutor(max_workers=6) as executor:
            metro_lines, metro_provider = self._resolve_category(
                "metro", lat, lon, radius_m, executor, durations
            )
            bus_lines, bus_provider = self._resolve_category(
                "bus", lat, lon, radius_m, executor, durations
            )
            taxis, taxi_provider = self._resolve_category(
                "taxi", lat, lon, radius_m, executor, durations
            )

        provider_used: dict[str, str] = {}
        if metro_provider:
            provider_used["metro"] = metro_provider
        if bus_provider:
            provider_used["bus"] = bus_provider
        if taxi_provider:
            provider_used["taxi"] = taxi_provider

        total_time = time.perf_counter() - start_total
        if SHOW_DEBUG and st is not None:
            st.caption(
                f"Transports: {total_time * 1000:.0f} ms (GTFS {durations['gtfs']:.2f}s, OSM {durations['osm']:.2f}s, Google {durations['google']:.2f}s)"
            )

        return TransportResult(
            metro_lines=metro_lines,
            bus_lines=bus_lines,
            taxis=taxis,
            provider_used=provider_used,
        )

    def _compute_sequential(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        durations: dict[str, float],
    ) -> TransportResult:
        metro_order = self._providers_for_mode("metro")
        bus_order = self._providers_for_mode("bus")
        taxi_order = self._providers_for_mode("taxi")
        metro_lines, metro_provider = self._compute_sequential_mode("metro", lat, lon, radius_m, metro_order, durations)
        bus_lines, bus_provider = self._compute_sequential_mode("bus", lat, lon, radius_m, bus_order, durations)
        taxis, taxi_provider = self._compute_sequential_mode("taxi", lat, lon, radius_m, taxi_order, durations)

        provider_used: dict[str, str] = {}
        if metro_provider:
            provider_used["metro"] = metro_provider
        if bus_provider:
            provider_used["bus"] = bus_provider
        if taxi_provider:
            provider_used["taxi"] = taxi_provider

        return TransportResult(
            metro_lines=metro_lines,
            bus_lines=bus_lines,
            taxis=taxis,
            provider_used=provider_used,
        )

    def _compute_sequential_mode(
        self,
        mode: str,
        lat: float,
        lon: float,
        radius_m: int,
        providers: Sequence[str],
        durations: dict[str, float],
    ) -> tuple[list[str], Optional[str]]:
        method_name = self._MODE_METHODS[mode]
        for name in providers:
            provider = self._get_provider(name)
            if provider is None:
                continue
            getter = getattr(provider, method_name, None)
            if not getter:
                continue
            start = time.perf_counter()
            try:
                lines = getter(lat, lon, radius_m)
            except Exception:
                durations[name] += time.perf_counter() - start
                continue
            durations[name] += time.perf_counter() - start
            normalized = self._normalize_lines(lines, TARGET_COUNT)
            if normalized:
                return normalized, name
        return [], None

    def get(self, lat: float, lon: float, radius_m: int = 1200) -> TransportResult:
        return self._compute(lat, lon, radius_m)

    def get_fast(self, lat: float, lon: float, radius_m: int = 1200) -> TransportResult:
        lat_q = round(lat, 5)
        lon_q = round(lon, 5)
        key = (id(self), lat_q, lon_q, int(radius_m))
        _SERVICE_REGISTRY[id(self)] = self
        try:
            return _cached_transport_result(key)
        except KeyError:
            return self._compute(lat, lon, radius_m)


@lru_cache(maxsize=128)
def _cached_transport_result(cache_key: tuple[int, float, float, int]) -> TransportResult:
    service_id, lat, lon, radius_m = cache_key
    service = _SERVICE_REGISTRY.get(service_id)
    if service is None:
        raise KeyError(service_id)
    return service._compute(lat, lon, radius_m)


__all__ = ["TransportResult", "TransportService"]
