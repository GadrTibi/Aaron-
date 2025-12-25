from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.generation_report import GenerationReport
from app.services.llm_client import invoke_llm_json
from app.services.text_limits import (
    MAX_QUARTIER_INTRO,
    MAX_TRANSPORT_BUS,
    MAX_TRANSPORT_METRO,
    MAX_TRANSPORT_TAXI,
)
from app.services.text_utils import truncate_clean
LEGACY_LLM_KEYS = {
    "transport_metro_texte": "transports_metro_texte",
    "transport_bus_texte": "transports_bus_texte",
    "transport_taxi_texte": "transports_taxi_texte",
}


SCHEMA = {
    "type": "object",
    "properties": {
        "quartier_intro": {"type": "string"},
        "transport_metro_texte": {"type": "string"},
        "transport_bus_texte": {"type": "string"},
        "transport_taxi_texte": {"type": "string"},
    },
    "required": [
        "quartier_intro",
        "transport_metro_texte",
        "transport_bus_texte",
        "transport_taxi_texte",
    ],
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _build_prompt(address: str) -> str:
    return (
        "Tu es un expert immobilier parisien. Rédige un court aperçu du quartier et des transports autour de l'adresse donnée.\n"
        "- Adresse : {address}\n"
        "- Contraintes style : concis, factuel, ton pro.\n"
        "- Sortie : JSON strict, pas d'autres textes.\n"
        "- Format des champs :\n"
        "  quartier_intro : 2-3 phrases max (ambiance, repères).\n"
        "  transport_metro_texte : 3-4 lignes max, format 'Ligne X (Station Y) - Xmin à pied'.\n"
        "  transport_bus_texte : 3-4 lignes max, format concis.\n"
        "  transport_taxi_texte : 1-2 lignes max ou 'Non disponible' si rien.\n"
        f"- Contraintes de longueur : quartier_intro max {MAX_QUARTIER_INTRO} caractères. Chaque champ transports_* doit faire max {MAX_TRANSPORT_METRO} caractères (espaces inclus).\n"
        "Réponds en JSON avec ce format exact et uniquement en JSON."
    ).format(address=address)


def _validate_payload(data: Dict[str, Any]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for key in (
        "quartier_intro",
        "transport_metro_texte",
        "transport_bus_texte",
        "transport_taxi_texte",
    ):
        legacy_key = LEGACY_LLM_KEYS.get(key, "")
        value = _clean(str(data.get(key, data.get(legacy_key, ""))))
        if not value:
            raise ValueError(f"Champ '{key}' manquant ou vide dans la réponse LLM.")
        output[key] = value
    return output


def enrich_quartier_and_transports(address: str, report: Optional[GenerationReport] = None) -> Dict[str, str]:
    addr = (address or "").strip()
    if not addr:
        raise ValueError("Adresse manquante pour l'enrichissement quartier/transports.")

    prompt = _build_prompt(addr)
    raw = invoke_llm_json(prompt, SCHEMA, report)
    validated = _validate_payload(raw)

    truncated_messages = []

    validated["quartier_intro"], truncated = truncate_clean(validated["quartier_intro"], MAX_QUARTIER_INTRO)
    if truncated:
        truncated_messages.append(f"Texte quartier tronqué à {MAX_QUARTIER_INTRO} caractères pour s’adapter au template.")

    validated["transport_metro_texte"], truncated = truncate_clean(validated["transport_metro_texte"], MAX_TRANSPORT_METRO)
    if truncated:
        truncated_messages.append(f"Texte métro tronqué à {MAX_TRANSPORT_METRO} caractères pour s’adapter au template.")

    validated["transport_bus_texte"], truncated = truncate_clean(validated["transport_bus_texte"], MAX_TRANSPORT_BUS)
    if truncated:
        truncated_messages.append(f"Texte bus tronqué à {MAX_TRANSPORT_BUS} caractères pour s’adapter au template.")

    validated["transport_taxi_texte"], truncated = truncate_clean(validated["transport_taxi_texte"], MAX_TRANSPORT_TAXI)
    if truncated:
        truncated_messages.append(f"Texte taxi tronqué à {MAX_TRANSPORT_TAXI} caractères pour s’adapter au template.")

    if report:
        for msg in truncated_messages:
            report.add_note(msg)

    return validated
