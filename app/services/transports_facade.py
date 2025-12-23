"""Cloud-friendly transport lookup façade with Streamlit caching.

This module prioritises lightweight Overpass lookups and optional enrichment
with Google Places (when a key is available). It is designed for Streamlit
Community Cloud where the filesystem is ephemeral, so it relies on
``st.cache_data`` instead of a custom disk cache.
"""

from __future__ import annotations

import importlib.util
import math
import time
from functools import lru_cache
from time import perf_counter
from typing import Any, Dict, Iterable, List, Tuple

import requests

from app.services.generation_report import GenerationReport
from app.services.overpass_client import query_overpass
from app.services.provider_status import resolve_api_key
from services.transports_v3 import GTFSProvider

spec = importlib.util.find_spec("streamlit")  # pragma: no cover - checked without import failure
if spec is not None:
    import streamlit as st  # type: ignore
else:  # pragma: no cover - streamlit not installed in tests
    st = None


CacheDict = Dict[str, float]
_GENERATION_TRACKER: CacheDict = {}

_TTL_SECONDS = 7 * 24 * 3600
_CACHE_ROUNDING = 4
_MAX_RESULTS = 10


def _round_coord(value: float, digits: int = _CACHE_ROUNDING) -> float:
    try:
        return round(float(value), digits)
    except Exception:
        return 0.0


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.radians
    dlat = rad(lat2 - lat1)
    dlon = rad(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371000 * c


def _cache_key(lat: float, lon: float, radius_m: int, mode: str, has_google: bool) -> str:
    return f"{lat}:{lon}:{int(radius_m)}:{mode}:{has_google}"


def _dedupe_sorted(values: Iterable[Tuple[float, str]], limit: int = _MAX_RESULTS) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for _, label in sorted(values, key=lambda x: x[0]):
        norm = label.strip()
        if not norm:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(norm)
        if len(result) >= limit:
            break
    return result


def _extract_coords(element: Dict[str, Any]) -> Tuple[float | None, float | None]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    center = element.get("center")
    if isinstance(center, dict):
        c_lat = center.get("lat")
        c_lon = center.get("lon")
        if c_lat is not None and c_lon is not None:
            return float(c_lat), float(c_lon)
    return None, None


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    radius = max(int(radius_m), 200)
    return (
        "[out:json][timeout:12];\n"
        "(\n"
        f"  node(around:{radius},{lat},{lon})[railway=station];\n"
        f"  node(around:{radius},{lat},{lon})[railway=tram_stop];\n"
        f"  node(around:{radius},{lat},{lon})[public_transport=stop_position];\n"
        f"  node(around:{radius},{lat},{lon})[public_transport=platform];\n"
        f"  node(around:{radius},{lat},{lon})[highway=bus_stop];\n"
        ");\n"
        "out tags center 150;"
    )


def _query_overpass_points(query: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return query_overpass(query, "transports_facade")


def _parse_overpass_elements(lat: float, lon: float, elements: Iterable[Dict[str, Any]]) -> Tuple[list[str], list[str]]:
    metro_candidates: list[tuple[float, str]] = []
    bus_candidates: list[tuple[float, str]] = []
    for element in elements:
        tags = element.get("tags") or {}
        lat2, lon2 = _extract_coords(element)
        if lat2 is None or lon2 is None:
            continue
        distance = _distance_m(lat, lon, lat2, lon2)
        is_bus = tags.get("highway") == "bus_stop" or tags.get("bus") == "yes"
        ref = tags.get("ref") or tags.get("name") or tags.get("public_transport") or ""
        label = str(ref).strip() or "Arrêt"
        if is_bus:
            bus_candidates.append((distance, label))
        else:
            metro_candidates.append((distance, label))
    return _dedupe_sorted(metro_candidates), _dedupe_sorted(bus_candidates)


def _fetch_overpass_data(lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
    warnings: list[str] = []
    query = _build_overpass_query(lat, lon, radius_m)
    try:
        elements, debug = _query_overpass_points(query)
    except requests.Timeout:
        debug = {"status": "timeout", "error": "timeout"}
        elements = []
    except Exception as exc:
        debug = {"status": "error", "error": str(exc)}
        elements = []

    if debug.get("status") in {"timeout"} or str(debug.get("error", "")).startswith("http_429"):
        warnings.append("Overpass indisponible (timeout ou 429)")
    metro_lines, bus_lines = _parse_overpass_elements(lat, lon, elements)
    return {
        "metro_lines": metro_lines,
        "bus_lines": bus_lines,
        "warnings": warnings,
        "debug": debug,
    }


def _google_api_key() -> str:
    value, _ = resolve_api_key("GOOGLE_MAPS_API_KEY")
    return value


def _enrich_with_google(lat: float, lon: float, radius_m: int, *, api_key: str) -> Dict[str, Any]:
    if not api_key:
        return {"metro_lines": [], "bus_lines": [], "warnings": ["Google Places indisponible (clé manquante)"], "debug": {"status": "disabled"}}
    payload = {
        "includedTypes": ["subway_station", "train_station", "bus_station", "transit_station"],
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius_m,
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.types",
    }
    warnings: list[str] = []
    try:
        response = requests.post("https://places.googleapis.com/v1/places:searchNearby", json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        warnings.append("Google Places timeout")
        return {"metro_lines": [], "bus_lines": [], "warnings": warnings, "debug": {"status": "timeout"}}
    except requests.RequestException as exc:  # pragma: no cover - network variability
        warnings.append(f"Google Places indisponible ({exc.__class__.__name__})")
        return {"metro_lines": [], "bus_lines": [], "warnings": warnings, "debug": {"status": "error"}}

    places = data.get("places") if isinstance(data, dict) else []
    metro: list[tuple[float, str]] = []
    bus: list[tuple[float, str]] = []
    for place in places or []:
        display = place.get("displayName") or {}
        name = display.get("text") if isinstance(display, dict) else None
        if not name:
            name = place.get("name")
        if not name:
            continue
        types = place.get("types") or []
        label = str(name).strip()
        if not label:
            continue
        category = "bus" if any(t.startswith("bus") for t in types) else "metro"
        if category == "bus":
            bus.append((0, label))
        else:
            metro.append((0, label))
    return {
        "metro_lines": _dedupe_sorted(metro),
        "bus_lines": _dedupe_sorted(bus),
        "warnings": warnings,
        "debug": {"status": "ok"},
    }


def _apply_gtfs_enrichment(lat: float, lon: float, radius_m: int, metro_lines: list[str], bus_lines: list[str]) -> Tuple[list[str], list[str]]:
    provider = GTFSProvider()
    remaining_metro = provider.get_metro_lines(lat, lon, radius_m)
    remaining_bus = provider.get_bus_lines(lat, lon, radius_m)
    merged_metro = _dedupe_sorted([(0, line) for line in metro_lines] + [(0, line) for line in remaining_metro])
    merged_bus = _dedupe_sorted([(0, line) for line in bus_lines] + [(0, line) for line in remaining_bus])
    return merged_metro, merged_bus


def _cache_decorator():
    if st is not None and hasattr(st, "cache_data"):
        return st.cache_data(ttl=_TTL_SECONDS)

    def wrapper(func):
        cached = lru_cache(maxsize=128)(func)
        cached.clear = cached.cache_clear  # type: ignore[attr-defined]
        return cached

    return wrapper


@_cache_decorator()
def _cached_transports(lat: float, lon: float, radius_m: int, mode: str, has_google: bool) -> Dict[str, Any]:
    data = _fetch_transports(lat, lon, radius_m, mode, has_google)
    if "generated_at" not in data:
        data = {**data, "generated_at": time.time()}
    return data


def _fetch_transports(lat: float, lon: float, radius_m: int, mode: str, has_google: bool) -> Dict[str, Any]:
    warnings: list[str] = []
    provider_used: dict[str, str] = {}
    debug: dict[str, Any] = {}

    overpass_data = _fetch_overpass_data(lat, lon, radius_m)
    metro_lines = list(overpass_data.get("metro_lines", []))
    bus_lines = list(overpass_data.get("bus_lines", []))
    warnings.extend(overpass_data.get("warnings", []))
    debug["overpass"] = overpass_data.get("debug", {})
    if metro_lines or bus_lines:
        provider_used.update({"metro": "overpass", "bus": "overpass"})

    if mode in {"ENRICHED", "FULL"} and has_google:
        google_data = _enrich_with_google(lat, lon, radius_m, api_key=_google_api_key())
        warnings.extend(google_data.get("warnings", []))
        debug["google"] = google_data.get("debug", {})
        if google_data.get("metro_lines"):
            metro_lines = _dedupe_sorted([(0, line) for line in metro_lines] + [(0, line) for line in google_data["metro_lines"]])
            provider_used["metro"] = provider_used.get("metro", "google")
        if google_data.get("bus_lines"):
            bus_lines = _dedupe_sorted([(0, line) for line in bus_lines] + [(0, line) for line in google_data["bus_lines"]])
            provider_used["bus"] = provider_used.get("bus", "google")
    elif mode in {"ENRICHED", "FULL"} and not has_google:
        warnings.append("Google Places désactivé (clé absente)")

    if mode == "FULL":
        metro_lines, bus_lines = _apply_gtfs_enrichment(lat, lon, radius_m, metro_lines, bus_lines)
        if metro_lines:
            provider_used.setdefault("metro", "gtfs")
        if bus_lines:
            provider_used.setdefault("bus", "gtfs")

    return {
        "metro_lines": metro_lines[:_MAX_RESULTS],
        "bus_lines": bus_lines[:_MAX_RESULTS],
        "taxis": [],
        "provider_used": provider_used,
        "warnings": warnings,
        "debug": debug,
    }


def get_transports(
    lat: float,
    lon: float,
    radius_m: int = 1200,
    mode: str = "FAST",
    report: GenerationReport | None = None,
) -> Dict[str, Any]:
    """Return nearby transports using a cache-friendly pipeline.

    Parameters
    ----------
    lat, lon : float
        Coordinates of the lookup.
    radius_m : int
        Search radius in meters (default 1200m).
    mode : str
        ``FAST`` (Overpass only), ``ENRICHED`` (Overpass + Google when
        available) or ``FULL`` (adds GTFS enrichment).
    report : GenerationReport | None
        Optional report to collect warnings for UI display.
    """

    safe_lat = _round_coord(lat)
    safe_lon = _round_coord(lon)
    mode_upper = (mode or "FAST").upper()
    has_google = bool(_google_api_key())
    cache_id = _cache_key(safe_lat, safe_lon, radius_m, mode_upper, has_google)

    start = perf_counter()
    raw_result = _cached_transports(safe_lat, safe_lon, radius_m, mode_upper, has_google)
    duration = perf_counter() - start

    generated_at = raw_result.get("generated_at")
    previous_gen = _GENERATION_TRACKER.get(cache_id)
    cache_status = "HIT" if previous_gen and generated_at == previous_gen else "MISS"
    if generated_at:
        _GENERATION_TRACKER[cache_id] = float(generated_at)

    payload = dict(raw_result)
    payload["cache_status"] = cache_status
    payload["duration_s"] = duration

    current_report = report or GenerationReport()
    for warning in raw_result.get("warnings", []):
        current_report.add_provider_warning(warning)

    return payload


def clear_transport_cache() -> None:
    """Clear local and Streamlit caches (used in tests)."""

    try:
        _cached_transports.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    _GENERATION_TRACKER.clear()


__all__ = ["get_transports", "clear_transport_cache"]
