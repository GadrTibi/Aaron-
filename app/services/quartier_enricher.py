from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from app.services.generation_report import GenerationReport
from app.services.text_constraints import (
    BUS_MAX_CHARS,
    BUS_MAX_LINES,
    METRO_MAX_CHARS,
    METRO_MAX_LINES,
    TAXI_MAX_CHARS,
    TAXI_MAX_LINES,
    enforce_limits,
)


def _format_context(context: Optional[dict]) -> str:
    if not context:
        return ""
    try:
        return json.dumps(context, ensure_ascii=False, indent=2)
    except Exception:
        return str(context)


@dataclass
class QuartierEnricher:
    """Generate concise quartier & transport texts while enforcing PPTX limits."""

    invoke_llm_json: Callable[[str], Dict[str, Any]]

    def build_prompt(self, context: Optional[dict] = None) -> str:
        context_block = _format_context(context)
        return (
            "Tu es Codex. Réponds uniquement en JSON avec les clés "
            '"transport_metro_texte", "transport_bus_texte", "transport_taxi_texte".\n'
            "Règles produit et format :\n"
            f'- Métro : max {METRO_MAX_LINES} lignes, format ultra concis type "L3 Villiers – 5min", '
            f"limite stricte {METRO_MAX_CHARS} caractères.\n"
            f'- Bus : max {BUS_MAX_LINES} lignes, format ultra concis type "30 Villiers – 2min", '
            f"limite stricte {BUS_MAX_CHARS} caractères.\n"
            f'- Taxi (optionnel) : 1 ligne max, format "Taxi: 2min", limite stricte {TAXI_MAX_CHARS} caractères.\n'
            "- Pas de phrases explicatives, pas de description comme \"Ces lignes offrent...\".\n"
            "- Pas de texte hors JSON, pas de paragraphes. 2-3 lignes maximum par champ.\n"
            "- Abréviations acceptées (L2, L3, etc.). Respecte strictement les limites de longueur en caractères.\n"
            "Contexte (aide uniquement) :\n"
            f"{context_block}\n"
            "JSON attendu : {\"transport_metro_texte\": \"...\", \"transport_bus_texte\": \"...\", \"transport_taxi_texte\": \"...\"}"
        )

    def enrich(self, context: Optional[dict] = None, *, report: Optional[GenerationReport] = None) -> Tuple[dict, GenerationReport]:
        prompt = self.build_prompt(context)
        raw = self.invoke_llm_json(prompt)
        base: dict[str, Any] = raw if isinstance(raw, dict) else {}

        final: dict[str, Any] = dict(base)
        final_report = report or GenerationReport()
        constraints = {
            "transport_metro_texte": (METRO_MAX_CHARS, METRO_MAX_LINES, "Metro"),
            "transport_bus_texte": (BUS_MAX_CHARS, BUS_MAX_LINES, "Bus"),
            "transport_taxi_texte": (TAXI_MAX_CHARS, TAXI_MAX_LINES, "Taxi"),
        }

        for key, (max_chars, max_lines, label) in constraints.items():
            original = str(base.get(key) or "")
            constrained = enforce_limits(original, max_chars, max_lines)
            final[key] = constrained
            if constrained != original:
                final_report.add_note(f"{label} trimmed to {len(constrained)} chars")

        return final, final_report
