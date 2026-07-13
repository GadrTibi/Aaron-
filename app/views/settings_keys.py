from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import tomllib  # Python 3.11+: lecture TOML
except Exception:  # pragma: no cover - tomllib indisponible
    tomllib = None  # type: ignore[assignment]

from app.services.key_tests import test_api_key
from app.services.provider_status import (
    ProviderInfo,
    delete_local_secret,
    has_local_secret,
    list_providers,
    local_secret_path,
    missing_essential_keys,
    openai_key_format_warning,
    redact_secret,
    resolve_api_key,
    write_local_secret,
)


# --------------------------------------------------------------------------- #
# Lecture de secret (conservée : utilisée hors UI, ex. services.transports_v3)
# --------------------------------------------------------------------------- #

def _dump_toml(d: Dict[str, Any]) -> str:
    lines = []
    for k, v in d.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            v_escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{v_escaped}"')
    return "\n".join(lines) + ("\n" if lines else "")


def _secrets_search_paths() -> list[Path]:
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
                out[key.strip()] = value.strip().strip('"').strip("'")
        except OSError:
            return {}
        return out
    try:
        return tomllib.loads(data.decode("utf-8"))
    except Exception:
        return {}


def read_local_secret(name: str, default: str = "") -> str:
    """Récupère un secret via environnement, st.secrets ou fichiers locaux."""
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
        payload = _read_toml_file(path)
        if name in payload and payload[name]:
            return str(payload[name])
    return default


# --------------------------------------------------------------------------- #
# UI — écran Clés API repensé (autonomie de l'utilisateur non-technique)
# --------------------------------------------------------------------------- #

def _rerun(st) -> None:
    fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if callable(fn):
        fn()


def _render_provider(st, p: ProviderInfo) -> None:
    value, source = resolve_api_key(p.key_name)

    # Entête : nom + pastille de statut
    if value:
        st.markdown(f"**{p.name}**  🟢 configurée")
        st.caption(f"{p.purpose}")
        st.caption(f"Clé détectée : `{redact_secret(value)}` — source : {source}")
    else:
        badge = "🔴 requise" if p.essential else "⚪ non configurée"
        st.markdown(f"**{p.name}**  {badge}")
        st.caption(p.purpose)

    new_val = st.text_input(
        f"Clé {p.name}",
        value="",
        type="password",
        key=f"in_{p.key_name}",
        placeholder="Collez votre clé ici puis « Enregistrer »",
        label_visibility="collapsed",
    )

    if p.key_name == "OPENAI_API_KEY" and new_val.strip():
        warning = openai_key_format_warning(new_val.strip())
        if warning:
            st.caption(f"⚠️ {warning}")

    cols = st.columns([1.2, 1, 1, 1.6])
    with cols[0]:
        if st.button("💾 Enregistrer", key=f"save_{p.key_name}", use_container_width=True):
            if new_val.strip():
                write_local_secret(p.key_name, new_val.strip())
                st.success("Clé enregistrée ✅")
                _rerun(st)
            else:
                st.warning("Saisissez une clé.")
    with cols[1]:
        if p.testable:
            if st.button("🧪 Tester", key=f"test_{p.key_name}", use_container_width=True):
                key_to_test = new_val.strip() or value
                if not key_to_test:
                    st.warning("Aucune clé à tester.")
                else:
                    ok, msg = test_api_key(p.key_name, key_to_test)
                    if ok is True:
                        st.success("Clé valide ✅")
                    elif ok is False:
                        st.error(f"Invalide : {msg}")
                    else:
                        st.info(msg)
    with cols[2]:
        if has_local_secret(p.key_name):
            if st.button("🗑️ Effacer", key=f"del_{p.key_name}", use_container_width=True):
                delete_local_secret(p.key_name)
                st.info("Clé locale effacée.")
                _rerun(st)
    with cols[3]:
        if p.signup_url:
            st.markdown(f"[Où obtenir cette clé ↗]({p.signup_url})")

    st.markdown("---")


def render(config):  # type: ignore[override]
    import streamlit as st

    st.subheader("🔑 Clés API")
    st.caption(
        "Configurez ici les accès nécessaires à l'application. Vos clés sont "
        f"enregistrées sur votre poste (`{local_secret_path()}`) et ne sont jamais partagées."
    )

    # Onboarding : état global des clés essentielles
    missing = missing_essential_keys()
    if missing:
        noms = ", ".join(p.name for p in missing)
        st.warning(
            f"⚠️ Clé(s) essentielle(s) manquante(s) : **{noms}**. "
            "Sans elles, les documents générés seront incomplets. Renseignez-les ci-dessous."
        )
    else:
        st.success("✅ Toutes les clés essentielles sont configurées. L'application est prête.")

    # Note Streamlit Cloud (persistance)
    if os.getenv("STREAMLIT_SHARING_MODE") or resolve_api_key("OPENAI_API_KEY")[1] == "st.secrets":
        st.info(
            "En ligne (Streamlit Cloud), la persistance durable des clés se fait via "
            "**Settings → Secrets** de l'application. L'enregistrement local ci-dessous peut "
            "être effacé après un redéploiement."
        )

    providers = list_providers()
    essentiels = [p for p in providers if p.essential]
    optionnels = [p for p in providers if not p.essential and p.requires_key]
    sans_cle = [p for p in providers if not p.requires_key]

    st.markdown("### Clés essentielles")
    for p in essentiels:
        _render_provider(st, p)

    if optionnels:
        with st.expander("Clés optionnelles — améliorent les images et les points d'intérêt"):
            for p in optionnels:
                _render_provider(st, p)

    if sans_cle:
        st.caption(
            "Sans clé requise : " + ", ".join(f"{p.name} ({p.purpose})" for p in sans_cle)
        )


__all__ = ["render", "read_local_secret", "write_local_secret"]
