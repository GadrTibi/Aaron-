from __future__ import annotations

import streamlit as st

from app.services.generation_report import GenerationReport
from app.services.geocode_cache import normalize_address
from app.services.geocoding_fallback import geocode_address_fallback


def ensure_geocoded(address: str, report: GenerationReport | None = None) -> tuple[float | None, float | None, str]:
    """Return coordinates for ``address`` using session cache or fallback providers.

    The helper stores the resulting coordinates and metadata in ``st.session_state``:
    ``geo_lat``, ``geo_lon``, ``geocode_provider`` and ``geocoded_address``.
    """

    normalized = normalize_address(address or "")
    if not normalized:
        raise ValueError("Adresse manquante pour le géocodage automatique.")

    session_lat = st.session_state.get("geo_lat")
    session_lon = st.session_state.get("geo_lon")
    session_addr = st.session_state.get("geocoded_address")
    if session_lat is not None and session_lon is not None and session_addr == normalized:
        return float(session_lat), float(session_lon), "session_cache"

    lat, lon, provider_used = geocode_address_fallback(normalized, report=report)
    st.session_state["geo_lat"] = lat
    st.session_state["geo_lon"] = lon
    st.session_state["geocode_provider"] = provider_used or ""
    st.session_state["geocoded_address"] = normalized
    return lat, lon, provider_used


__all__ = ["ensure_geocoded"]
