"""Utility helpers to geocode a human readable address."""

from __future__ import annotations

import logging
import os

import requests

LOGGER = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "MFYLocalApp/1.0 (+https://github.com/Aaron-/MFY-Local-App)"


def _headers() -> dict[str, str]:
    """Return headers accepted by the public Nominatim API.

    The service requires a meaningful User-Agent that includes contact info.
    Users can override it with the ``MFY_NOMINATIM_USER_AGENT`` or the more
    generic ``MFY_HTTP_USER_AGENT`` environment variable.
    """

    ua = os.getenv("MFY_NOMINATIM_USER_AGENT") or os.getenv("MFY_HTTP_USER_AGENT")
    if not ua:
        ua = DEFAULT_USER_AGENT
    return {"User-Agent": ua}


def geocode_address(q: str) -> tuple[float | None, float | None]:
    """Return latitude/longitude for an address or ``(None, None)`` on failure."""

    if not q or not q.strip():
        return (None, None)

    params = {"q": q, "format": "json", "limit": 1, "addressdetails": 0}
    try:
        response = requests.get(NOMINATIM_URL, params=params, headers=_headers(), timeout=20)
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - network failures depend on env
        LOGGER.warning("Nominatim rejected query %s: %s", q, exc)
        return (None, None)
    except requests.RequestException as exc:  # pragma: no cover - network failures depend on env
        LOGGER.warning("Nominatim request failed for %s: %s", q, exc)
        return (None, None)

    data = response.json()
    if not data:
        return (None, None)

    try:
        return (float(data[0]["lat"]), float(data[0]["lon"]))
    except (KeyError, ValueError, TypeError):
        return (None, None)