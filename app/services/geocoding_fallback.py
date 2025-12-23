"""Geocoding helpers with multi-provider fallback and reporting."""

from __future__ import annotations

import logging
from typing import Callable, Tuple

import requests

from app.services.generation_report import GenerationReport
from app.services.geocode import geocode_address as geocode_nominatim
from app.services.provider_status import resolve_api_key

LOGGER = logging.getLogger(__name__)


def _geocode_geoapify(address: str, api_key: str, http_get: Callable[..., requests.Response]) -> Tuple[float | None, float | None]:
    url = "https://api.geoapify.com/v1/geocode/search"
    params = {"text": address, "format": "json", "limit": 1, "apiKey": api_key}
    response = http_get(url, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    features = data.get("features") or []
    if not features:
        return None, None
    props = features[0].get("properties") or {}
    lat = props.get("lat")
    lon = props.get("lon")
    try:
        return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def _geocode_google(address: str, api_key: str, http_get: Callable[..., requests.Response]) -> Tuple[float | None, float | None]:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    response = http_get(url, params=params, timeout=15)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or []
    if not results:
        return None, None
    location = results[0].get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lon = location.get("lng")
    try:
        return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def geocode_address_fallback(
    address: str,
    report: GenerationReport | None = None,
    *,
    http_get: Callable[..., requests.Response] | None = None,
) -> tuple[float | None, float | None, str]:
    """Geocode with fallback: Nominatim -> Geoapify -> Google.

    Returns ``(lat, lon, provider_used)`` and adds warnings to ``report`` when
    fallbacks are triggered or errors occur.
    """

    http = http_get or requests.get
    rep = report or GenerationReport()
    providers_order = ["Nominatim", "Geoapify", "Google"]
    tried: list[str] = []

    # 1) Nominatim (existing helper)
    try:
        lat, lon = geocode_nominatim(address)
    except Exception as exc:  # pragma: no cover - defensive guard
        rep.add_provider_warning(f"Nominatim échec: {exc}")
        lat, lon = None, None
    if lat is not None and lon is not None:
        return lat, lon, providers_order[0]
    tried.append("Nominatim")

    # 2) Geoapify
    geo_key, source_geo = resolve_api_key("GEOAPIFY_API_KEY")
    if geo_key:
        try:
            lat, lon = _geocode_geoapify(address, geo_key, http)
        except Exception as exc:
            rep.add_provider_warning(f"Geoapify géocodage indisponible ({source_geo}): {exc}")
            lat, lon = None, None
        if lat is not None and lon is not None:
            rep.add_provider_warning("Fallback géocodage: Geoapify utilisé après Nominatim.")
            return lat, lon, providers_order[1]
        tried.append("Geoapify")

    # 3) Google
    g_key, source_g = resolve_api_key("GOOGLE_MAPS_API_KEY")
    if g_key:
        try:
            lat, lon = _geocode_google(address, g_key, http)
        except Exception as exc:
            rep.add_provider_warning(f"Google géocodage indisponible ({source_g}): {exc}")
            lat, lon = None, None
        if lat is not None and lon is not None:
            rep.add_provider_warning("Fallback géocodage: Google utilisé après échecs précédents.")
            return lat, lon, providers_order[2]
        tried.append("Google")

    if not tried:
        rep.add_provider_warning("Aucun provider de géocodage disponible.")
    else:
        rep.add_provider_warning(f"Géocodage indisponible (tentatives: {', '.join(tried)}).", blocking=True)
    return None, None, ""


__all__ = ["geocode_address_fallback"]
