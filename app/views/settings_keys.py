from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

import streamlit as st


SECRETS_DIR = Path.home() / ".mfy_local_app"
SECRETS_FILE = SECRETS_DIR / "secrets.toml"


def _ensure_secrets_dir() -> None:
    try:
        SECRETS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(SECRETS_DIR, 0o700)
    except OSError:
        # Ignore permission errors: directory might already have stricter perms
        pass


def _load_local_secrets() -> Dict[str, str]:
    if not SECRETS_FILE.exists():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover
        return {}
    try:
        with SECRETS_FILE.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def read_local_secret(name: str) -> str:
    if not name:
        return ""
    env_value = os.environ.get(name)
    if env_value:
        return env_value
    secrets_obj = getattr(st, "secrets", None)
    if secrets_obj and name in secrets_obj:
        value = secrets_obj.get(name)
        if value:
            return str(value)
    local_secrets = _load_local_secrets()
    return local_secrets.get(name, "")


def _serialise_secrets(data: Dict[str, str]) -> str:
    def _escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f'"{escaped}"'

    lines = [f"{key} = {_escape(value)}" for key, value in sorted(data.items())]
    return "\n".join(lines) + ("\n" if lines else "")


def write_local_secret(name: str, value: str) -> None:
    if not name:
        return
    _ensure_secrets_dir()
    secrets = _load_local_secrets()
    secrets[name] = value
    payload = _serialise_secrets(secrets)
    with SECRETS_FILE.open("w", encoding="utf-8") as fh:
        fh.write(payload)
    try:
        os.chmod(SECRETS_FILE, 0o600)
    except OSError:
        pass


def render(_config: Dict[str, str] | None = None) -> None:
    st.header("Paramètres")
    st.subheader("Clés API")

    existing_key = read_local_secret("GOOGLE_MAPS_API_KEY")
    if existing_key:
        suffix = existing_key[-4:] if len(existing_key) >= 4 else existing_key
        masked = f"••••{suffix}"
        st.success(f"Clé Google: OK ({masked})")
    else:
        st.warning("Clé Google manquante.")

    new_value = st.text_input(
        "GOOGLE_MAPS_API_KEY",
        value="",
        type="password",
        help="Collez ici votre clé Google Maps Places.",
    )
    if st.button("Enregistrer"):
        write_local_secret("GOOGLE_MAPS_API_KEY", new_value.strip())
        st.success("Clé enregistrée localement.")
        st.experimental_rerun()


__all__ = ["render", "read_local_secret", "write_local_secret"]
