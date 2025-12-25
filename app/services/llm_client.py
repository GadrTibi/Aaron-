from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import requests

from app.services.provider_status import resolve_api_key
from app.services.generation_report import GenerationReport


DEFAULT_MODEL = os.environ.get("MFY_OPENAI_MODEL", "gpt-4o-mini")
RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT = 30
REQUIRED_FIELDS = {
    "quartier_intro",
    "transports_metro_texte",
    "transports_bus_texte",
    "transports_taxi_texte",
}


def _get_openai_api_key() -> str:
    key, _ = resolve_api_key("OPENAI_API_KEY")
    if key:
        return key
    raise RuntimeError(
        "Clé OpenAI absente (OPENAI_API_KEY). Ajoutez la clé (env, st.secrets ou ~/.mfy_local_app/secrets.toml) puis réessayez."
    )


def _openai_post(url: str, payload: dict, api_key: str, timeout_s: int) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    if response.status_code >= 400:
        try:
            data = response.json()
            error = data.get("error", {}) if isinstance(data, dict) else {}
            message = error.get("message") or str(error) or response.text
            code = error.get("code")
            suffix = f" ({code})" if code else ""
            raise RuntimeError(f"OpenAI error {response.status_code}: {message}{suffix}")
        except ValueError:
            snippet = (response.text or "")[:500]
            raise RuntimeError(f"OpenAI error {response.status_code}: {snippet}")
    return response.json()


def _build_structured_payload(prompt: str, schema: Dict[str, Any]) -> dict:
    return {
        "model": DEFAULT_MODEL,
        "input": [
            {"role": "system", "content": "Tu réponds STRICTEMENT en JSON conforme au schéma."},
            {"role": "user", "content": prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "quartier_transports",
                "schema": schema,
                "strict": True,
            }
        },
        "temperature": 0.2,
    }


def _build_json_object_payload(prompt: str) -> dict:
    return {
        "model": DEFAULT_MODEL,
        "input": [
            {"role": "system", "content": "Tu réponds STRICTEMENT en JSON valide."},
            {"role": "user", "content": prompt},
        ],
        "text": {"format": {"type": "json_object"}},
        "temperature": 0.2,
    }


def _extract_output_text(response: dict) -> Any:
    if response is None:
        return None
    if "output_text" in response:
        return response.get("output_text")

    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text")

    # Structured outputs can already be the JSON object
    return response


def _parse_response_payload(response: dict) -> Dict[str, Any]:
    payload = _extract_output_text(response)
    if payload is None:
        raise RuntimeError("Réponse OpenAI vide.")

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Le LLM n'a pas renvoyé de JSON valide.") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Le LLM a répondu dans un format inattendu.")

    missing = REQUIRED_FIELDS - set(payload.keys())
    if missing:
        raise RuntimeError(f"Champs manquants dans la réponse LLM: {', '.join(sorted(missing))}")

    return payload


def _should_fallback(exc: Exception) -> bool:
    msg = str(exc).lower()
    if "openai error 400" not in msg:
        return False
    return any(keyword in msg for keyword in ("format", "schema", "json_schema", "response_format", "strict"))


def invoke_llm_json(prompt: str, schema: Dict[str, Any], report: Optional[GenerationReport] = None) -> Dict[str, Any]:
    if not prompt or not prompt.strip():
        raise ValueError("Prompt LLM vide ou invalide.")

    api_key = _get_openai_api_key()
    structured_payload = _build_structured_payload(prompt, schema)
    json_object_payload = _build_json_object_payload(prompt)

    try:
        response = _openai_post(RESPONSES_URL, structured_payload, api_key, REQUEST_TIMEOUT)
        return _parse_response_payload(response)
    except RuntimeError as exc:
        if _should_fallback(exc):
            if report is not None:
                report.add_provider_warning(f"OpenAI: structured outputs failed, fallback to json_object ({exc})")
            try:
                response = _openai_post(RESPONSES_URL, json_object_payload, api_key, REQUEST_TIMEOUT)
                return _parse_response_payload(response)
            except RuntimeError as fallback_exc:
                if report is not None:
                    report.add_provider_warning(str(fallback_exc))
                raise
        if report is not None:
            report.add_provider_warning(str(exc))
        raise
