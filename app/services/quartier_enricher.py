from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.services.geo_helpers import ensure_geocoded
from app.services.generation_report import GenerationReport
from app.services.llm_client import invoke_llm_json
from app.services.provider_status import resolve_api_key
from app.services.quartier_sanitize import sanitize_intro
from app.services.taxi_stands import build_taxi_lines_from_stands, find_nearby_taxi_stands
from app.services.transports_compact import build_compact_transport_texts
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
        "- Format et longueur max des champs :\n"
        "  quartier_intro (220-280 caractères) : format obligatoire \"Quartier <NOM_QUARTIER> (17e) — <ambiance/commerces>\".\n"
        "    Si le nom du quartier est inconnu, utiliser \"Dans le 17e arrondissement — <ambiance>\".\n"
        "    Ne pas commencer par l'adresse.\n"
        "  transport_metro_texte : NE DOIT contenir que la liste des lignes (ex: \"2, 12\" ou \"2, 12, 3bis\"), sans station ni minutes.\n"
        "  transport_bus_texte : NE DOIT contenir que la liste des lignes (ex: \"30, 40, 54, 95\"), sans arrêt ni minutes.\n"
        "  transport_taxi_texte : doit être exactement \"Stations de taxi\" (ou vide si inconnue, l'app gère le fallback).\n"
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

    taxi_override = _compute_taxi_from_google(addr, report=report)
    prompt = _build_prompt(addr)
    raw = invoke_llm_json(prompt, SCHEMA, report)
    validated = _validate_payload(raw)
    before_sanitize = dict(validated)
    if taxi_override:
        validated["transport_taxi_texte"] = taxi_override
    compact_transports = build_compact_transport_texts(
        validated.get("transport_metro_texte", ""),
        validated.get("transport_bus_texte", ""),
        validated.get("transport_taxi_texte", ""),
    )
    sanitized = {
        "quartier_intro": sanitize_intro(validated.get("quartier_intro", ""), addr),
        "transport_metro_texte": compact_transports["transport_metro_texte"],
        "transport_bus_texte": compact_transports["transport_bus_texte"],
        "transport_taxi_texte": compact_transports["transport_taxi_texte"],
    }
    if report is not None:
        report.quartier_sanitize_debug = {"avant": before_sanitize, "apres": sanitized}
        if (
            sanitized["transport_metro_texte"] != validated.get("transport_metro_texte")
            or sanitized["transport_bus_texte"] != validated.get("transport_bus_texte")
            or sanitized["transport_taxi_texte"] != validated.get("transport_taxi_texte")
        ):
            report.add_note("Transports reformattés au format compact (lignes).")
    return sanitized


def _compute_taxi_from_google(address: str, report: Optional[GenerationReport] = None) -> str | None:
    api_key, _ = resolve_api_key("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None
    lat: float | None = None
    lon: float | None = None
    try:
        lat, lon, _ = ensure_geocoded(address, report=report)
    except Exception:
        return None
    if lat is None or lon is None:
        return None
    try:
        stands = find_nearby_taxi_stands(lat, lon, api_key=api_key)
    except Exception as exc:
        if report is not None:
            report.add_provider_warning(f"Taxis Google indisponibles: {exc}")
        return "Taxis: G7/Uber disponibles (2–5 min)"
    if stands:
        return build_taxi_lines_from_stands(stands)
    return "Taxis: G7/Uber disponibles (2–5 min)"
