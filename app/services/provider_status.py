"""Helpers to introspect provider configuration without network calls."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

try:
    import tomllib  # Python 3.11
except ModuleNotFoundError:  # pragma: no cover - fallback for old runtimes
    tomllib = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    env_keys: Iterable[str]
    requires_key: bool = True


def _read_toml(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    if tomllib is None:
        return {}
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    cleaned: Dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = str(value)
    return cleaned


def _streamlit_secrets() -> Dict[str, str]:
    spec = importlib.util.find_spec("streamlit")
    if spec is None:
        return {}
    streamlit = importlib.import_module("streamlit")
    secrets_obj = getattr(streamlit, "secrets", None)
    if secrets_obj is None:
        return {}
    try:
        return {k: str(v) for k, v in secrets_obj.items() if v}
    except Exception:
        return {}


def _default_secret_paths() -> list[Path]:
    return [
        Path.home() / ".mfy_local_app" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.cwd() / "app" / ".streamlit" / "secrets.toml",
    ]


def resolve_api_key(
    key_name: str,
    *,
    secret_paths: Iterable[Path] | None = None,
) -> Tuple[str, str]:
    """Resolve an API key from environment, Streamlit or local files.

    Returns
    -------
    tuple
        (value, source) where source is one of ``env``, ``st.secrets``,
        ``local_file`` or ``missing``.
    """

    if not key_name:
        return "", "missing"

    env_val = os.getenv(key_name)
    if env_val:
        return str(env_val), "env"

    secrets = _streamlit_secrets()
    if key_name in secrets and secrets[key_name]:
        return secrets[key_name], "st.secrets"

    for path in secret_paths or _default_secret_paths():
        payload = _read_toml(path)
        if key_name in payload and payload[key_name]:
            return str(payload[key_name]), "local_file"

    return "", "missing"


def _provider_definitions() -> list[ProviderInfo]:
    return [
        ProviderInfo("Google Places", ["GOOGLE_MAPS_API_KEY"]),
        ProviderInfo("OpenAI", ["OPENAI_API_KEY"]),
        ProviderInfo("Geoapify", ["GEOAPIFY_API_KEY"]),
        ProviderInfo("OpenTripMap", ["OPENTRIPMAP_API_KEY"]),
        ProviderInfo("Unsplash", ["UNSPLASH_ACCESS_KEY"]),
        ProviderInfo("Pexels", ["PEXELS_API_KEY"]),
        ProviderInfo("Wikimedia", [], requires_key=False),
    ]


def get_provider_status() -> dict[str, dict[str, object]]:
    """Return a status summary for all providers without network calls."""

    status: dict[str, dict[str, object]] = {}
    for provider in _provider_definitions():
        key_value = ""
        key_source = "missing"
        if provider.requires_key:
            # use first declared env key
            first_key = next(iter(provider.env_keys), "")
            key_value, key_source = resolve_api_key(first_key)
        has_key = bool(key_value) if provider.requires_key else True
        enabled = has_key if provider.requires_key else True
        note = ""
        if provider.requires_key and not has_key:
            note = "clé manquante -> fallback activé"
        elif not provider.requires_key:
            note = "aucune clé requise"
        status[provider.name] = {
            "enabled": bool(enabled),
            "has_key": bool(has_key),
            "key_source": key_source if provider.requires_key else "missing",
            "notes": note,
        }
    return status


__all__ = [
    "ProviderInfo",
    "get_provider_status",
    "resolve_api_key",
]
