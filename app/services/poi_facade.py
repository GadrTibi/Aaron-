"""POI lookup with provider fallback and reporting."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List

from app.services.generation_report import GenerationReport
from app.services.provider_status import get_provider_status
from services.places_geoapify import GeoapifyPlacesService, Place
from services.places_google import GPlace, GooglePlacesService
from services.places_otm import OpenTripMapService, Visit
from services.wiki_poi import POI, WikiPOIService

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class POIResult:
    name: str
    distance_m: float | None
    provider: str
    raw: object


def _map_google(service: GooglePlacesService, lat: float, lon: float, radius_m: int, categories: Iterable[str]) -> Dict[str, List[POIResult]]:
    mapping: Dict[str, List[GPlace]] = {}
    for cat in categories:
        if cat == "incontournables":
            mapping[cat] = service.list_incontournables(lat, lon, radius_m)
        elif cat == "spots":
            mapping[cat] = service.list_spots(lat, lon, radius_m)
        elif cat == "visits":
            mapping[cat] = service.list_visits(lat, lon, radius_m)
    return {k: [_to_result(p.name, p.distance_m, "Google Places", p) for p in v] for k, v in mapping.items()}


def _map_geoapify(service: GeoapifyPlacesService, lat: float, lon: float, radius_m: int, categories: Iterable[str]) -> Dict[str, List[POIResult]]:
    mapping: Dict[str, List[Place]] = {}
    for cat in categories:
        if cat == "incontournables":
            mapping[cat] = service.list_incontournables(lat, lon, radius_m)
        elif cat == "spots":
            mapping[cat] = service.list_spots(lat, lon, radius_m)
    return {k: [_to_result(p.name, p.distance_m, "Geoapify", p) for p in v] for k, v in mapping.items()}


def _map_otm(service: OpenTripMapService, lat: float, lon: float, radius_m: int, categories: Iterable[str]) -> Dict[str, List[POIResult]]:
    mapping: Dict[str, List[Visit]] = {}
    if "visits" in categories:
        mapping["visits"] = service.list_visits(lat, lon, radius_m)
    return {k: [_to_result(v.name, v.distance_m, "OpenTripMap", v) for v in vals] for k, vals in mapping.items()}


def _map_wiki(service: WikiPOIService, lat: float, lon: float, radius_m: int, categories: Iterable[str]) -> Dict[str, List[POIResult]]:
    mapping: Dict[str, List[POI]] = {}
    grouped = service.list_by_category(lat, lon, radius_m)
    for cat in categories:
        if cat in grouped:
            mapping[cat] = grouped[cat]
    return {k: [_to_result(p.name_display, p.distance_m, "Wikimedia", p) for p in v] for k, v in mapping.items()}


def _to_result(name: str, distance: float | None, provider: str, raw: object) -> POIResult:
    return POIResult(name=name or "Lieu", distance_m=distance if distance is not None else None, provider=provider, raw=raw)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _extract_lat_lon(raw: object) -> tuple[float | None, float | None]:
    if raw is None:
        return None, None
    for attr in ("lat", "latitude"):
        if hasattr(raw, attr):
            lat_val = getattr(raw, attr)
            if lat_val is not None:
                lat = float(lat_val)
                break
    else:
        lat = None
    for attr in ("lon", "longitude"):
        if hasattr(raw, attr):
            lon_val = getattr(raw, attr)
            if lon_val is not None:
                lon = float(lon_val)
                break
    else:
        lon = None
    if lat is not None and lon is not None:
        return lat, lon
    if isinstance(raw, dict):
        lat_val = raw.get("lat") or raw.get("latitude")
        lon_val = raw.get("lon") or raw.get("longitude")
        try:
            return float(lat_val), float(lon_val)
        except (TypeError, ValueError):
            return None, None
    return None, None


def filter_poi_results(
    lat: float,
    lon: float,
    radius_m: int,
    results: Dict[str, List[POIResult]],
) -> Dict[str, List[POIResult]]:
    filtered: Dict[str, List[POIResult]] = {}
    for category, items in results.items():
        kept: List[POIResult] = []
        for item in items:
            distance = item.distance_m
            if distance is None:
                lat_val, lon_val = _extract_lat_lon(item.raw)
                if lat_val is None or lon_val is None:
                    continue
                distance = _haversine_m(lat, lon, lat_val, lon_val)
            if distance <= radius_m:
                if item.distance_m is None:
                    item = POIResult(name=item.name, distance_m=distance, provider=item.provider, raw=item.raw)
                kept.append(item)
        kept.sort(key=lambda entry: entry.distance_m if entry.distance_m is not None else float("inf"))
        filtered[category] = kept
    return filtered


def _provider_order(custom: Iterable[str] | None) -> List[str]:
    if custom:
        return [p.lower() for p in custom]
    return ["google", "geoapify", "opentripmap", "wikimedia"]


def _is_enabled(status: dict[str, dict[str, object]], key: str) -> bool:
    for name, entry in status.items():
        if name.lower().startswith(key):
            return bool(entry.get("enabled"))
    return False


def get_pois(
    lat: float,
    lon: float,
    radius_m: int,
    categories: Iterable[str],
    report: GenerationReport | None = None,
    preferred_order: Iterable[str] | None = None,
) -> Dict[str, List[POIResult]]:
    """Return POIs for requested categories with provider fallback."""

    rep = report or GenerationReport()
    cats = list(categories)
    provider_status = get_provider_status()
    order = _provider_order(preferred_order)
    if order:
        primary = order[0]
        if primary == "google" and not _is_enabled(provider_status, "google"):
            rep.add_provider_warning("Google Places non disponible (clé manquante) : activation du fallback.")

    for provider_key in order:
        if provider_key == "google":
            if not _is_enabled(provider_status, "google"):
                continue
            try:
                g_key, _ = resolve_google_key()
                service = GooglePlacesService(g_key)
                results = filter_poi_results(lat, lon, radius_m, _map_google(service, lat, lon, radius_m, cats))
            except Exception as exc:
                rep.add_provider_warning(f"Google Places indisponible: {exc}")
                continue
            if any(results.values()):
                return results
            rep.add_provider_warning("Google Places n'a retourné aucun résultat, tentative d'un fallback.")
            continue

        if provider_key == "geoapify":
            if not _is_enabled(provider_status, "geoapify"):
                continue
            try:
                g_key, _ = resolve_geoapify_key()
                service = GeoapifyPlacesService(api_key=g_key)
                results = filter_poi_results(lat, lon, radius_m, _map_geoapify(service, lat, lon, radius_m, cats))
            except Exception as exc:
                rep.add_provider_warning(f"Geoapify indisponible: {exc}")
                continue
            if any(results.values()):
                rep.add_provider_warning("Fallback POI utilisé: Geoapify.")
                return results
            rep.add_provider_warning("Geoapify n'a retourné aucun résultat, tentative d'un autre provider.")
            continue

        if provider_key in ("opentripmap", "otm"):
            if not _is_enabled(provider_status, "opentripmap"):
                continue
            try:
                otm_key, _ = resolve_opentripmap_key()
                service = OpenTripMapService(api_key=otm_key)
                results = filter_poi_results(lat, lon, radius_m, _map_otm(service, lat, lon, radius_m, cats))
            except Exception as exc:
                rep.add_provider_warning(f"OpenTripMap indisponible: {exc}")
                continue
            if any(results.values()):
                rep.add_provider_warning("Fallback POI utilisé: OpenTripMap.")
                return results
            rep.add_provider_warning("OpenTripMap n'a retourné aucun résultat, tentative d'un autre provider.")
            continue

        if provider_key == "wikimedia":
            try:
                service = WikiPOIService()
                results = filter_poi_results(lat, lon, radius_m, _map_wiki(service, lat, lon, radius_m, cats))
            except Exception as exc:
                rep.add_provider_warning(f"Wikimedia POI indisponible: {exc}")
                continue
            if any(results.values()):
                rep.add_provider_warning("Fallback POI utilisé: Wikimedia.")
                return results
            rep.add_provider_warning("Wikimedia n'a retourné aucun résultat.")
            continue

    rep.add_provider_warning("Aucun provider POI disponible ou résultats vides.", blocking=True)
    return {cat: [] for cat in cats}


def build_spots_and_visits(
    lat: float,
    lon: float,
    radius_m: int,
    report: GenerationReport | None = None,
    preferred_order: Iterable[str] | None = None,
) -> Dict[str, List[POIResult]]:
    results = get_pois(
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        categories=("spots", "visits"),
        report=report,
        preferred_order=preferred_order,
    )
    return {
        "spots": results.get("spots", []),
        "visits": results.get("visits", []),
    }


def resolve_google_key() -> tuple[str, str]:
    from app.services.provider_status import resolve_api_key

    return resolve_api_key("GOOGLE_MAPS_API_KEY")


def resolve_geoapify_key() -> tuple[str, str]:
    from app.services.provider_status import resolve_api_key

    return resolve_api_key("GEOAPIFY_API_KEY")


def resolve_opentripmap_key() -> tuple[str, str]:
    from app.services.provider_status import resolve_api_key

    return resolve_api_key("OPENTRIPMAP_API_KEY")


__all__ = ["build_spots_and_visits", "filter_poi_results", "get_pois", "POIResult"]
