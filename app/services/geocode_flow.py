"""Small helpers to orchestrate geocoding flows without Streamlit runtime."""

from __future__ import annotations

from app.services.geocode_cache import normalize_address


def should_use_session_cache(address: str, session_address: str | None, lat: float | None, lon: float | None) -> bool:
    """Decide whether session coordinates can be reused for an address."""

    if lat is None or lon is None:
        return False
    return normalize_address(address) == normalize_address(session_address or "")


__all__ = ["should_use_session_cache"]
