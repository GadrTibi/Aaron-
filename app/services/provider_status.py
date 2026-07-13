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
    essential: bool = False          # requis pour un document complet
    purpose: str = ""                # à quoi sert la clé (affiché à l'utilisateur)
    signup_url: str = ""             # où obtenir la clé
    testable: bool = False           # un bouton "Tester" est proposé

    @property
    def key_name(self) -> str:
        """Nom canonique de la clé (1re clé d'environnement déclarée)."""
        return next(iter(self.env_keys), "")


def _read_toml(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    if tomllib is None:
        # Runtime cible = Python >= 3.11 (CDC : 3.12+), tomllib toujours présent.
        # Le secret local en TOML n'est de toute façon utilisé qu'en dev ; en
        # production Streamlit Cloud les clés passent par st.secrets.
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
        local_secret_path(),
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.cwd() / "app" / ".streamlit" / "secrets.toml",
    ]


def local_secret_path() -> Path:
    return Path.home() / ".mfy_local_app" / "secrets.toml"


def read_local_secrets() -> Dict[str, str]:
    return _read_toml(local_secret_path())


def write_local_secret(name: str, value: str) -> None:
    if not name:
        return
    target = local_secret_path()
    try:
        payload = _read_toml(target) if target.exists() else {}
    except Exception:
        payload = {}
    payload[name] = str(value)
    _write_toml(target, payload)


def delete_local_secret(name: str) -> None:
    if not name:
        return
    target = local_secret_path()
    try:
        payload = _read_toml(target) if target.exists() else {}
    except Exception:
        payload = {}
    if name not in payload:
        return
    payload.pop(name, None)
    _write_toml(target, payload)


def has_local_secret(name: str) -> bool:
    payload = read_local_secrets()
    return bool(payload.get(name))


def _write_toml(path: Path, payload: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, v in payload.items():
        escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{k} = "{escaped}"')
    try:
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


def redact_secret(value: str) -> str:
    if not value:
        return "ABSENTE"
    if len(value) <= 10:
        return f"{value[:2]}****"
    return f"{value[:3]}****...{value[-4:]}"


def openai_key_format_warning(value: str) -> str:
    if not value or value.startswith("sk-") or value.startswith("sk-proj-"):
        return ""
    return "Format inattendu : une clé OpenAI commence généralement par 'sk-' ou 'sk-proj-'."


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
        ProviderInfo(
            "OpenAI", ["OPENAI_API_KEY"], essential=True, testable=True,
            purpose="Rédige l'introduction du quartier et les textes de transports (métro, bus, taxi).",
            signup_url="https://platform.openai.com/api-keys",
        ),
        ProviderInfo(
            "Google Maps Platform", ["GOOGLE_MAPS_API_KEY"], essential=True, testable=True,
            purpose="Recherche les points d'intérêt du quartier (incontournables, spots, lieux à visiter).",
            signup_url="https://console.cloud.google.com/google/maps-apis/credentials",
        ),
        ProviderInfo(
            "Geoapify", ["GEOAPIFY_API_KEY"], essential=False,
            purpose="Solution de secours pour les points d'intérêt et le géocodage (facultatif).",
            signup_url="https://myprojects.geoapify.com/",
        ),
        ProviderInfo(
            "OpenTripMap", ["OPENTRIPMAP_API_KEY"], essential=False,
            purpose="Source complémentaire de lieux touristiques (facultatif).",
            signup_url="https://opentripmap.io/product",
        ),
        # NB : Unsplash / Pexels retirés (2026-07) — leur seul consommateur était
        # app/services/image_fetcher.py, supprimé. Ne pas réafficher sans un
        # consommateur réel (une clé sans effet trompe l'utilisateur).
        ProviderInfo(
            "Wikimedia", [], requires_key=False, essential=False,
            purpose="Images et informations de lieux connus. Aucune clé requise.",
        ),
    ]


def list_providers() -> list[ProviderInfo]:
    """Liste publique des fournisseurs (pour l'écran Clés API et les indicateurs)."""
    return _provider_definitions()


def missing_essential_keys() -> list[ProviderInfo]:
    """Fournisseurs ESSENTIELS dont la clé est absente (pour l'onboarding/alerte)."""
    out = []
    for p in _provider_definitions():
        if p.essential and p.requires_key:
            value, _ = resolve_api_key(p.key_name)
            if not value:
                out.append(p)
    return out


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
    "delete_local_secret",
    "get_provider_status",
    "has_local_secret",
    "list_providers",
    "local_secret_path",
    "missing_essential_keys",
    "openai_key_format_warning",
    "read_local_secrets",
    "redact_secret",
    "resolve_api_key",
    "write_local_secret",
]
