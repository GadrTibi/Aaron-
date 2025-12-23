"""Utility helpers to geocode a human readable address."""

from __future__ import annotations

import logging
import os
from typing import Callable

import requests

LOGGER = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "MFY-Local-App/1.0"
DEFAULT_TIMEOUT = 10


def _user_agent(custom_ua: str | None = None) -> str:
    """Return a stable User-Agent accepted by the public Nominatim API.

    The service requires a meaningful User-Agent that includes contact info.
    Users can override it with ``MFY_USER_AGENT`` and we also keep backwards
    compatibility with ``MFY_NOMINATIM_USER_AGENT`` / ``MFY_HTTP_USER_AGENT``.
    """

    return (
        custom_ua
        or os.getenv("MFY_USER_AGENT")
        or os.getenv("MFY_NOMINATIM_USER_AGENT")
        or os.getenv("MFY_HTTP_USER_AGENT")
        or DEFAULT_USER_AGENT
    )


def _headers(user_agent: str | None = None) -> dict[str, str]:
    return {"User-Agent": _user_agent(user_agent)}


def geocode_address(
    q: str,
    *,
    http_get: Callable[..., requests.Response] | None = None,
    user_agent: str | None = None,
    timeout: float | int = DEFAULT_TIMEOUT,
) -> tuple[float | None, float | None]:
    """Return latitude/longitude for an address or ``(None, None)`` on failure.

    Errors are allowed to propagate so that callers can decide whether to
    trigger a fallback or display richer diagnostics.
    """

    if not q or not q.strip():
        raise ValueError("Adresse vide ou invalide pour le géocodage")

    params = {"q": q, "format": "json", "limit": 1, "addressdetails": 0}
    http = http_get or requests.get
    response = http(NOMINATIM_URL, params=params, headers=_headers(user_agent), timeout=timeout)
    response.raise_for_status()

    data = response.json()
    if not data:
        return (None, None)

    try:
        return (float(data[0]["lat"]), float(data[0]["lon"]))
    except (KeyError, ValueError, TypeError):
        return (None, None)
