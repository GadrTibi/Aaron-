from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib  # Python 3.11: lecture TOML
except Exception:  # pragma: no cover - tomllib indisponible
    tomllib = None  # type: ignore[assignment]

from app.services.provider_status import get_provider_status


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


def write_local_secret(name: str, value: str) -> None:
    if not name:
        return

    target = Path.home() / ".mfy_local_app" / "secrets.toml"
    try:
        payload = _read_toml_file(target) if target.exists() else {}
    except Exception:
        payload = {}
    payload[name] = value
    _write_toml_file(target, payload)


# --- UI RENDER (ajuste la section qui lit/affiche la clé) ---
def render(config):  # type: ignore[override]
    import streamlit as st

    st.subheader("Clés API")
    existing_key = read_local_secret("GOOGLE_MAPS_API_KEY", "")
    masked = ("…" + existing_key[-4:]) if existing_key else "ABSENTE"
    st.caption(f"Clé Google détectée: {masked}")

    new_val = st.text_input(
        "GOOGLE_MAPS_API_KEY",
        value="",
        type="password",
        help="Collez votre clé Google Maps Platform.",
    )
    if st.button("Enregistrer"):
        if new_val.strip():
            write_local_secret("GOOGLE_MAPS_API_KEY", new_val.strip())
            st.success("Clé enregistrée localement (~/.mfy_local_app/secrets.toml). Relancez la page.")
        else:
            st.warning("Aucune valeur saisie.")

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
