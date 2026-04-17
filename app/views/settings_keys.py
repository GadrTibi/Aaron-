from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib  # Python 3.11: lecture TOML
except Exception:  # pragma: no cover - tomllib indisponible
    tomllib = None  # type: ignore[assignment]

from app.services.llm_client import test_openai_api_key
from app.services.provider_status import (
    delete_local_secret,
    get_provider_status,
    has_local_secret,
    local_secret_path,
    openai_key_format_warning,
    redact_secret,
    resolve_api_key,
    write_local_secret,
)


# Ecriture TOML simple sans dépendance externe

def _dump_toml(d: Dict[str, Any]) -> str:
    """Serialise un dictionnaire simple vers TOML."""
    lines = []
    for k, v in d.items():
        if isinstance(v, str):
            v_escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{v_escaped}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            v_str = str(v)
            v_escaped = v_str.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{v_escaped}"')
    return "\n".join(lines) + ("\n" if lines else "")


def _secrets_search_paths() -> list[Path]:
    """Retourne les chemins possibles pour secrets.toml."""
    return [
        Path.home() / ".mfy_local_app" / "secrets.toml",
        Path.cwd() / ".streamlit" / "secrets.toml",
        Path.cwd() / "app" / ".streamlit" / "secrets.toml",
    ]


def _read_toml_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if tomllib is None:
        out: Dict[str, Any] = {}
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                out[key] = value
        except OSError:
            return {}
        return out
    try:
        return tomllib.loads(data.decode("utf-8"))
    except Exception:
        return {}


def _write_toml_file(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(_dump_toml(payload), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


def read_local_secret(name: str, default: str = "") -> str:
    """Récupère un secret localement ou via l'environnement."""
    if not name:
        return default

    env_value = os.getenv(name)
    if env_value:
        return env_value

    try:
        import streamlit as st  # peut ne pas exister hors runtime

        secrets_obj = getattr(st, "secrets", None)
        if secrets_obj is not None:
            try:
                value = secrets_obj.get(name, "")
                if value:
                    return str(value)
            except Exception:
                pass
    except Exception:
        pass

    for path in _secrets_search_paths():
        try:
            payload = _read_toml_file(path)
        except Exception:
            continue
        if name in payload and payload[name]:
            return str(payload[name])

    return default


def _render_key_block(st, *, title: str, key_name: str, help_text: str) -> None:
    detected_value, key_source = resolve_api_key(key_name)
    masked = redact_secret(detected_value)
    if masked == "ABSENTE":
        st.caption(f"Clé {title} absente (source: absente)")
    else:
        st.caption(f"Clé {title} détectée: {masked} (source: {key_source})")

    new_val = st.text_input(
        key_name,
        value="",
        type="password",
        help=help_text,
        key=f"input_{key_name.lower()}",
    )
    col_save, col_clear = st.columns([2, 1])
    with col_save:
        if st.button("Enregistrer", key=f"save_{key_name.lower()}"):
            if new_val.strip():
                write_local_secret(key_name, new_val.strip())
                st.success("Clé enregistrée localement (~/.mfy_local_app/secrets.toml). Relancez la page.")
            else:
                st.warning("Aucune valeur saisie.")
    with col_clear:
        if has_local_secret(key_name):
            if st.button("Effacer la clé locale", key=f"clear_{key_name.lower()}"):
                delete_local_secret(key_name)
                st.info("Clé locale effacée.")


def _render_openai_block(st) -> None:
    st.markdown("### OpenAI")
    detected_value, key_source = resolve_api_key("OPENAI_API_KEY")
    if detected_value:
        st.caption(f"Clé OpenAI détectée : {redact_secret(detected_value)} (source: {key_source})")
    else:
        st.caption("Clé OpenAI absente (source: absente)")

    show_value = st.checkbox("Afficher la saisie OpenAI", value=False, key="show_openai_key")
    new_val = st.text_input(
        "OpenAI API Key",
        value="",
        type="default" if show_value else "password",
        key="input_openai_api_key",
        help="Clé OpenAI utilisée pour l'enrichissement LLM.",
    )
    format_warning = openai_key_format_warning(new_val.strip())
    if format_warning:
        st.warning(format_warning)

    if key_source == "st.secrets" or os.getenv("STREAMLIT_SHARING_MODE"):
        st.info(
            "En Streamlit Cloud, la persistance durable se fait via Settings > Secrets. "
            "L’enregistrement local ici n’est pas garanti après redéploiement."
        )

    col_save, col_test, col_delete = st.columns([2, 1.3, 1.5])
    with col_save:
        if st.button("Enregistrer localement", key="save_openai_api_key"):
            if not new_val.strip():
                st.warning("La clé OpenAI ne doit pas être vide.")
            else:
                write_local_secret("OPENAI_API_KEY", new_val.strip())
                st.success(f"Clé enregistrée localement ({local_secret_path()}).")
    with col_test:
        if st.button("Tester la clé", key="test_openai_api_key"):
            key_to_test = new_val.strip() or detected_value
            if not key_to_test:
                st.warning("Aucune clé OpenAI à tester.")
            else:
                ok, message = test_openai_api_key(key_to_test)
                if ok:
                    st.success("Clé valide")
                else:
                    st.error(f"Clé invalide / erreur OpenAI: {message}")
    with col_delete:
        if st.button("Supprimer la clé locale", key="delete_openai_api_key"):
            if has_local_secret("OPENAI_API_KEY"):
                delete_local_secret("OPENAI_API_KEY")
                st.info("Clé locale OpenAI supprimée.")
            else:
                st.caption("Aucune clé locale OpenAI à supprimer.")


# --- UI RENDER (ajuste la section qui lit/affiche la clé) ---
def render(config):  # type: ignore[override]
    import streamlit as st

    st.subheader("Clés API")
    _render_key_block(
        st,
        title="Google Maps Platform",
        key_name="GOOGLE_MAPS_API_KEY",
        help_text="Collez votre clé Google Maps Platform.",
    )
    st.markdown("---")
    _render_openai_block(st)

    st.markdown("---")
    st.subheader("Statut des fournisseurs")
    status = get_provider_status()
    table = []
    for name, info in status.items():
        table.append(
            {
                "Fournisseur": name,
                "Actif": "✅" if info.get("enabled") else "❌",
                "Clé": "✅" if info.get("has_key") else "❌",
                "Source": info.get("key_source", "missing"),
                "Notes": info.get("notes", ""),
            }
        )
    if table:
        st.table(table)


__all__ = ["render", "read_local_secret", "write_local_secret"]
