"""Cloud-friendly transport lookup façade with Streamlit caching.

This module prioritises lightweight Overpass lookups and optional enrichment
with Google Places (when a key is available). It is designed for Streamlit
Community Cloud where the filesystem is ephemeral, so it relies on
``st.cache_data`` instead of a custom disk cache.
"""

from __future__ import annotations

import importlib.util
import math
import re
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
_MAX_RESULTS = 4
_DEFAULT_TAXI_DESTINATION = "Paris, Opéra"


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


def normalize_name(name: str | None) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(r"\s+", " ", text)
    for prefix in ("bus ", "ligne "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def _dedupe_labels(values: Iterable[str], limit: int = _MAX_RESULTS) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for label in values:
        norm = normalize_name(label)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        clean = str(label).strip()
        if clean:
            result.append(clean)
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


def _build_station_query(lat: float, lon: float, radius_m: int) -> str:
    radius = max(int(radius_m), 200)
    return (
        "[out:json][timeout:12];\n"
        "(\n"
        f"  nwr(around:{radius},{lat},{lon})[railway~\"^(station|halt)$\"];\n"
        f"  nwr(around:{radius},{lat},{lon})[station=subway];\n"
        f"  nwr(around:{radius},{lat},{lon})[railway=tram_stop];\n"
        f"  nwr(around:{radius},{lat},{lon})[public_transport=station];\n"
        ");\n"
        "out tags center 50;"
    )


def _build_bus_query(lat: float, lon: float, radius_m: int) -> str:
    radius = max(int(radius_m), 200)
    return (
        "[out:json][timeout:12];\n"
        "(\n"
        f"  nwr(around:{radius},{lat},{lon})[highway=bus_stop];\n"
        ");\n"
        "out tags center 50;"
    )


def _query_overpass_points(query: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    return query_overpass(query, "transports_facade")


def _finalize_entries(candidates: Iterable[Dict[str, Any]], *, prefix: str) -> list[str]:
    labels: list[str] = []
    sorted_candidates = sorted(
        candidates,
        key=lambda item: item.get("distance_m") if item.get("distance_m") is not None else float("inf"),
    )
    for entry in sorted_candidates:
        name = str(entry.get("name") or entry.get("ref") or prefix).strip()
        norm = normalize_name(name)
        if not norm:
            continue
        label = f"{prefix} {name}" if prefix else name
        distance = entry.get("distance_m")
        distance_int: int | None
        if distance is not None:
            try:
                distance_int = int(round(float(distance)))
            except Exception:
                distance_int = None
        else:
            distance_int = None
        if distance_int is not None:
            label = f"{label} ({distance_int} m)"
        labels.append(label)
    return _dedupe_labels(labels)


def _parse_overpass_elements(lat: float, lon: float, elements: Iterable[Dict[str, Any]], *, default_label: str) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    for element in elements:
        tags = element.get("tags") or {}
        lat2, lon2 = _extract_coords(element)
        if lat2 is None or lon2 is None:
            continue
        distance = _distance_m(lat, lon, lat2, lon2)
        name = tags.get("name") or tags.get("ref") or default_label
        candidates.append({"name": str(name).strip() or default_label, "ref": tags.get("ref"), "distance_m": distance})
    return candidates


def _fetch_overpass_data(lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
    warnings: list[str] = []
    start_total = perf_counter()

    station_query = _build_station_query(lat, lon, radius_m)
    bus_query = _build_bus_query(lat, lon, radius_m)

    def _run_query(query: str, label: str) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        try:
            elements, dbg = _query_overpass_points(query)
        except requests.Timeout:
            return [], {"status": "timeout", "label": label}
        except Exception as exc:
            return [], {"status": "error", "label": label, "error": str(exc)}
        dbg = dbg or {}
        dbg.setdefault("label", label)
        dbg.setdefault("items", len(elements))
        return elements, dbg

    station_elements, station_debug = _run_query(station_query, "stations")
    bus_elements, bus_debug = _run_query(bus_query, "bus")

    if station_debug.get("status") in {"timeout"} or str(station_debug.get("error", "")).startswith("http_429"):
        warnings.append("Overpass indisponible (timeout ou 429) pour les stations")
    if bus_debug.get("status") in {"timeout"} or str(bus_debug.get("error", "")).startswith("http_429"):
        warnings.append("Overpass indisponible (timeout ou 429) pour les arrêts de bus")

    metro_candidates = _parse_overpass_elements(lat, lon, station_elements, default_label="Station")
    bus_candidates = _parse_overpass_elements(lat, lon, bus_elements, default_label="Arrêt de bus")

    metro_lines = _finalize_entries(metro_candidates, prefix="Station")
    bus_lines = _finalize_entries(bus_candidates, prefix="Arrêt")

    duration_ms = int((perf_counter() - start_total) * 1000)
    overpass_debug = {
        "metro": {**station_debug, "raw_items": len(station_elements), "kept": len(metro_lines)},
        "bus": {**bus_debug, "raw_items": len(bus_elements), "kept": len(bus_lines)},
        "duration_ms": duration_ms,
    }

    return {
        "metro_lines": metro_lines,
        "bus_lines": bus_lines,
        "warnings": warnings,
        "debug": overpass_debug,
        "raw_counts": {"metro": len(station_elements), "bus": len(bus_elements)},
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
        "metro_lines": _dedupe_labels([label for _, label in metro]),
        "bus_lines": _dedupe_labels([label for _, label in bus]),
        "warnings": warnings,
        "debug": {"status": "ok"},
    }


def _apply_gtfs_enrichment(lat: float, lon: float, radius_m: int, metro_lines: list[str], bus_lines: list[str]) -> Tuple[list[str], list[str]]:
    provider = GTFSProvider()
    remaining_metro = provider.get_metro_lines(lat, lon, radius_m)
    remaining_bus = provider.get_bus_lines(lat, lon, radius_m)
    merged_metro = _dedupe_labels(list(metro_lines) + list(remaining_metro))
    merged_bus = _dedupe_labels(list(bus_lines) + list(remaining_bus))
    return merged_metro, merged_bus


def _normalize_entries(items: Iterable[str | Dict[str, Any]], *, prefix: str) -> list[str]:
    normalized: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("ref") or prefix
        else:
            name = item
        if not name:
            continue
        label = f"{prefix} {name}".strip() if prefix else str(name).strip()
        normalized.append(label)
    return _dedupe_labels(normalized)


def _estimate_taxi_time(lat: float, lon: float, *, api_key: str, destination: str = _DEFAULT_TAXI_DESTINATION) -> list[str]:
    if not api_key:
        return []
    params = {
        "destinations": destination,
        "origins": f"{lat},{lon}",
        "mode": "driving",
        "key": api_key,
    }
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/distancematrix/json", params=params, timeout=8)
        response.raise_for_status()
        data = response.json()
        rows = data.get("rows") if isinstance(data, dict) else []
        if not rows:
            return []
        elements = rows[0].get("elements") if isinstance(rows[0], dict) else []
        if not elements:
            return []
        duration = elements[0].get("duration") or {}
        seconds = duration.get("value")
        if seconds is None:
            return []
        minutes = int(round(float(seconds) / 60.0))
        return [f"Temps de voiture estimé: {minutes} min (vers {destination})"]
    except requests.Timeout:
        return []
    except requests.RequestException:
        return []


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

    raw_counts = overpass_data.get("raw_counts", {})
    raw_metro = raw_counts.get("metro", 0)
    raw_bus = raw_counts.get("bus", 0)

    if mode in {"ENRICHED", "FULL"} and has_google:
        google_data = _enrich_with_google(lat, lon, radius_m, api_key=_google_api_key())
        warnings.extend(google_data.get("warnings", []))
        debug["google"] = google_data.get("debug", {})
        if google_data.get("metro_lines"):
            metro_lines = _dedupe_labels(
                list(metro_lines) + _normalize_entries(google_data["metro_lines"], prefix="Station")
            )
            provider_used["metro"] = provider_used.get("metro", "google")
        if google_data.get("bus_lines"):
            bus_lines = _dedupe_labels(
                list(bus_lines) + _normalize_entries(google_data["bus_lines"], prefix="Arrêt")
            )
            provider_used["bus"] = provider_used.get("bus", "google")
    elif mode in {"ENRICHED", "FULL"} and not has_google:
        warnings.append("Google Places désactivé (clé absente)")

    if mode == "FULL":
        metro_lines, bus_lines = _apply_gtfs_enrichment(lat, lon, radius_m, metro_lines, bus_lines)
        if metro_lines:
            provider_used.setdefault("metro", "gtfs")
        if bus_lines:
            provider_used.setdefault("bus", "gtfs")

    taxis: list[str] = []
    if mode == "FAST":
        taxis = ["Non calculé (mode FAST)"]
    elif has_google:
        taxis = _estimate_taxi_time(lat, lon, api_key=_google_api_key()) or []

    return {
        "metro_lines": metro_lines[:_MAX_RESULTS],
        "bus_lines": bus_lines[:_MAX_RESULTS],
        "taxis": taxis,
        "provider_used": provider_used,
        "warnings": warnings,
        "debug": debug,
        "raw_counts": {"metro": raw_metro, "bus": raw_bus},
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
