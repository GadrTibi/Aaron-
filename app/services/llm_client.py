from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests

from app.services.generation_report import GenerationReport


DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
REQUEST_TIMEOUT = 30


def _get_openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key

    try:
        import streamlit as st

        secrets = getattr(st, "secrets", None)
        if secrets and secrets.get("OPENAI_API_KEY"):
            return str(secrets["OPENAI_API_KEY"])
    except Exception:
        # Streamlit non disponible ou secrets inaccessibles : ignorer silencieusement
        pass

    raise RuntimeError("Clé OpenAI absente (OPENAI_API_KEY). Ajoutez la clé avant de réessayer.")


def invoke_llm_json(prompt: str, schema: Dict[str, Any], report: Optional[GenerationReport] = None) -> Dict[str, Any]:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt LLM vide ou invalide.")

    api_key = _get_openai_api_key()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": "Tu es un assistant qui répond uniquement en JSON valide."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object", "schema": schema},
        "temperature": 0.2,
    }

    try:
        response = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
    except Exception as exc:  # noqa: BLE001
        if report is not None:
            report.add_provider_warning(f"LLM indisponible : {exc}")
        raise RuntimeError("Enrichissement indisponible pour le moment. Merci de réessayer plus tard.") from exc

    if not content:
        if report is not None:
            report.add_provider_warning("LLM : réponse vide reçue.")
        raise RuntimeError("Le LLM n'a pas retourné de contenu exploitable.")

    try:
        parsed = json.loads(content)
    except Exception as exc:  # noqa: BLE001
        if report is not None:
            report.add_provider_warning("LLM : réponse non JSON.")
        raise RuntimeError("Le LLM n'a pas renvoyé de JSON valide.") from exc

    if not isinstance(parsed, dict):
        if report is not None:
            report.add_provider_warning("LLM : format JSON inattendu.")
        raise RuntimeError("Le LLM a répondu dans un format inattendu.")

    return parsed
