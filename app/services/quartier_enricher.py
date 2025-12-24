from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.generation_report import GenerationReport
from app.services.llm_client import invoke_llm_json


SCHEMA = {
    "type": "object",
    "properties": {
        "quartier_intro": {"type": "string"},
        "transports_metro_texte": {"type": "string"},
        "transports_bus_texte": {"type": "string"},
        "transports_taxi_texte": {"type": "string"},
    },
    "required": [
        "quartier_intro",
        "transports_metro_texte",
        "transports_bus_texte",
        "transports_taxi_texte",
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
        "  transports_metro_texte : 3-4 lignes max, format 'Ligne X (Station Y) - Xmin à pied'.\n"
        "  transports_bus_texte : 3-4 lignes max, format concis.\n"
        "  transports_taxi_texte : 1-2 lignes max ou 'Non disponible' si rien.\n"
        "Réponds en JSON avec ce format exact et uniquement en JSON."
    ).format(address=address)


def _validate_payload(data: Dict[str, Any]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for key in (
        "quartier_intro",
        "transports_metro_texte",
        "transports_bus_texte",
        "transports_taxi_texte",
    ):
        value = _clean(str(data.get(key, "")))
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
    return _validate_payload(raw)
