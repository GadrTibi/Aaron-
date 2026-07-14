"""Tests de validité des clés API, centralisés pour l'écran Clés API.

Chaque test renvoie ``(ok, message)`` :
- ``ok is True``  -> clé valide,
- ``ok is False`` -> clé invalide / erreur (message court, sans fuite de secret),
- ``ok is None``  -> aucun test disponible pour ce fournisseur.
"""

from __future__ import annotations

from typing import Optional, Tuple

import requests

from app.services.llm_client import test_openai_api_key
from app.services.provider_status import redact_secret

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def _redact(msg: str, key: str) -> str:
    msg = (msg or "").replace("\n", " ").strip()
    if key:
        msg = msg.replace(key, redact_secret(key))
    return msg[:180] or "erreur inconnue"


def test_google_maps_key(api_key: str) -> Tuple[bool, str]:
    key = (api_key or "").strip()
    if not key:
        return False, "clé absente"
    try:
        resp = requests.get(GEOCODE_URL, params={"address": "Paris, France", "key": key}, timeout=10)
    except Exception as exc:  # noqa: BLE001
        return False, _redact(str(exc), key)
    try:
        data = resp.json()
    except ValueError:
        return False, f"réponse inattendue ({resp.status_code})"
    status = data.get("status")
    if status == "OK":
        return True, "ok"
    # REQUEST_DENIED / INVALID_REQUEST / OVER_QUERY_LIMIT...
    return False, _redact(data.get("error_message") or status or "clé refusée", key)


# Routage : nom de clé -> fonction de test
_TESTERS = {
    "OPENAI_API_KEY": lambda v: test_openai_api_key(v),
    "GOOGLE_MAPS_API_KEY": test_google_maps_key,
}


def test_api_key(key_name: str, value: str) -> Tuple[Optional[bool], str]:
    tester = _TESTERS.get(key_name)
    if tester is None:
        return None, "Aucun test automatique disponible pour cette clé."
    return tester(value)


__all__ = ["test_api_key", "test_google_maps_key"]
