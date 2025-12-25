from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any


# Tokens attendus sur la slide quartier/transports des templates Estimation.
ESTIMATION_QUARTIER_TRANSPORT_TOKENS: set[str] = {
    "[[QUARTIER_INTRO]]",
    "[[TRANSPORT_METRO_TEXTE]]",
    "[[TRANSPORT_BUS_TEXTE]]",
    "[[TRANSPORT_TAXI_TEXTE]]",
    # Optionnel selon les templates : même contenu que [[QUARTIER_INTRO]]
    "[[QUARTIER_TEXTE]]",
}

QUARTIER_TRANSPORT_SESSION_KEYS: tuple[str, ...] = (
    "quartier_intro",
    "transport_metro_texte",
    "transport_bus_texte",
    "transport_taxi_texte",
)

LEGACY_TRANSPORT_SESSION_KEYS = {
    "transports_metro_texte": "transport_metro_texte",
    "transports_bus_texte": "transport_bus_texte",
    "transports_taxi_texte": "transport_taxi_texte",
}


def migrate_quartier_transport_session(state: MutableMapping[str, Any]) -> None:
    """
    Copie les anciennes clés ``transports_*`` vers les clés canoniques ``transport_*``
    si ces dernières sont absentes ou vides. Fait de même pour le pending éventuel.
    """

    pending = state.get("_quartier_pending")
    if isinstance(pending, dict):
        for legacy, canonical in LEGACY_TRANSPORT_SESSION_KEYS.items():
            if canonical not in pending and pending.get(legacy):
                pending[canonical] = pending[legacy]

    for legacy, canonical in LEGACY_TRANSPORT_SESSION_KEYS.items():
        if state.get(canonical):
            continue
        legacy_value = state.get(legacy)
        if legacy_value:
            state[canonical] = legacy_value


def build_quartier_transport_tokens_mapping(values: Mapping[str, Any]) -> dict[str, str]:
    """Construit le mapping Slide 4 (quartier/transports) à partir de valeurs canoniques."""

    quartier_intro = str(values.get("quartier_intro") or "").strip()
    transport_metro_texte = str(values.get("transport_metro_texte") or "").strip()
    transport_bus_texte = str(values.get("transport_bus_texte") or "").strip()
    transport_taxi_texte = str(values.get("transport_taxi_texte") or "").strip()

    mapping = {
        "[[QUARTIER_INTRO]]": quartier_intro,
        "[[TRANSPORT_METRO_TEXTE]]": transport_metro_texte,
        "[[TRANSPORT_BUS_TEXTE]]": transport_bus_texte,
        "[[TRANSPORT_TAXI_TEXTE]]": transport_taxi_texte,
    }

    if "[[QUARTIER_TEXTE]]" in ESTIMATION_QUARTIER_TRANSPORT_TOKENS:
        mapping["[[QUARTIER_TEXTE]]"] = quartier_intro

    return mapping
