from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.generation_report import GenerationReport
from app.services.llm_client import invoke_llm_json
from app.services.text_constraints import (
    BUS_MAX_CHARS,
    BUS_MAX_LINES,
    METRO_MAX_CHARS,
    METRO_MAX_LINES,
    TAXI_MAX_CHARS,
    TAXI_MAX_LINES,
    enforce_limits,
)
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
        "- Contraintes style : ultra concis, factuel, ton pro.\n"
        "- Sortie : JSON strict, pas d'autres textes.\n"
        "- Formats imposés (pas de phrases, pas d'explications, seulement les lignes demandées) :\n"
        "  quartier_intro : 2-3 phrases max (ambiance, repères).\n"
        "  transport_metro_texte : max 3 lignes, ex: \"L3 Villiers – 5min\" (≤ {metro_max} caractères).\n"
        "  transport_bus_texte : max 3 lignes, ex: \"30 Villiers – 2min\" (≤ {bus_max} caractères).\n"
        "  transport_taxi_texte : 1 ligne, ex: \"Taxi: 2min\" ou \"Non disponible\" (≤ {taxi_max} caractères).\n"
        "Abréviations acceptées (L2, L3, etc.). Pas de texte additionnel.\n"
        "Réponds en JSON avec ce format exact et uniquement en JSON."
    ).format(address=address, metro_max=METRO_MAX_CHARS, bus_max=BUS_MAX_CHARS, taxi_max=TAXI_MAX_CHARS)


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

    metro = enforce_limits(validated["transport_metro_texte"], METRO_MAX_CHARS, METRO_MAX_LINES)
    bus = enforce_limits(validated["transport_bus_texte"], BUS_MAX_CHARS, BUS_MAX_LINES)
    taxi = enforce_limits(validated["transport_taxi_texte"], TAXI_MAX_CHARS, TAXI_MAX_LINES)

    if report is not None:
        if metro != validated["transport_metro_texte"]:
            report.add_note(f"Metro trimmed to {len(metro)} chars")
        if bus != validated["transport_bus_texte"]:
            report.add_note(f"Bus trimmed to {len(bus)} chars")
        if taxi != validated["transport_taxi_texte"]:
            report.add_note(f"Taxi trimmed to {len(taxi)} chars")

    validated["transport_metro_texte"] = metro
    validated["transport_bus_texte"] = bus
    validated["transport_taxi_texte"] = taxi
    return validated
