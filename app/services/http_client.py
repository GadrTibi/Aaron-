"""Couche HTTP commune : un seul point pour les appels réseau JSON, avec timeout,
retry et backoff exponentiel sur les erreurs TRANSITOIRES (429, 5xx, timeouts,
erreurs de connexion). Respecte l'en-tête ``Retry-After`` quand il est présent.

Objectif : fiabiliser les appels aux API externes (OpenAI, Google, Geoapify…) sans
que chaque service réimplémente sa propre logique de retry.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

# Statuts HTTP qu'il vaut la peine de réessayer (transitoires).
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_S = 0.5
# Plafond DUR de l'attente entre deux tentatives : empêche qu'un `Retry-After`
# serveur abusif (ex. « 3600 ») ne gèle le thread de rendu Streamlit (appel
# synchrone). Au-delà, on préfère abandonner le retry que figer l'UI.
MAX_SLEEP_S = 20.0


def _retry_after_seconds(resp: requests.Response) -> Optional[float]:
    # Seule la forme ENTIÈRE (secondes) est gérée. La forme HTTP-date autorisée
    # par la spec (« Wed, 21 Oct 2015… ») est ignorée → repli sûr sur le backoff
    # exponentiel. Suffisant pour nos providers (OpenAI/Google renvoient des secondes).
    value = resp.headers.get("Retry-After")
    if value and value.strip().isdigit():
        return float(value.strip())
    return None


def request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff: float = DEFAULT_BACKOFF_S,
    retry_on_timeout: bool = True,
    sleep=time.sleep,
    **kwargs,
) -> requests.Response:
    """``requests.request`` durci. Retourne la ``Response`` finale.

    - Réessaie sur les statuts ``RETRYABLE_STATUS`` et (si ``retry_on_timeout``) sur
      ``requests.Timeout`` / ``requests.ConnectionError``, jusqu'à ``max_retries`` fois.
    - Backoff exponentiel (``backoff * 2**tentative``) ou ``Retry-After``, **plafonné
      à ``MAX_SLEEP_S``**.
    - Les erreurs non transitoires (4xx hors 429) sont renvoyées telles quelles.
    - ``retry_on_timeout=False`` pour une requête NON idempotente (mutation, upload,
      paiement) : un timeout ne doit pas être rejoué (risque de double effet).
    - ``sleep`` est injectable (tests).
    """
    last_exc: Optional[Exception] = None
    resp: Optional[requests.Response] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if retry_on_timeout and attempt < max_retries:
                sleep(min(backoff * (2 ** attempt), MAX_SLEEP_S))
                continue
            raise
        if resp.status_code in RETRYABLE_STATUS and attempt < max_retries:
            wait = _retry_after_seconds(resp) or backoff * (2 ** attempt)
            sleep(min(wait, MAX_SLEEP_S))
            continue
        return resp
    if last_exc is not None:
        raise last_exc
    return resp  # type: ignore[return-value]


def get(url: str, **kwargs) -> requests.Response:
    return request_with_retry("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    """POST avec retry. ⚠️ Réservé aux POST IDEMPOTENTS (génération LLM, recherche).
    Pour une mutation non idempotente, passer ``retry_on_timeout=False``."""
    return request_with_retry("POST", url, **kwargs)


__all__ = ["request_with_retry", "get", "post", "RETRYABLE_STATUS"]
