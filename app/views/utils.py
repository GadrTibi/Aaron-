import os
import re
from collections.abc import MutableMapping
import streamlit as st

from app.services.generation_report import GenerationReport
from app.services.template_validation import ValidationResult

def _sanitize_filename(name: str, ext: str) -> str:
    base = os.path.basename(name)
    safe = re.sub(r"[^A-Za-z0-9 _\-.]", "_", base)
    if not safe.lower().endswith(f".{ext}"):
        safe += f".{ext}"
    return safe

@st.cache_data(ttl=5)
def list_templates(dirpath: str, ext: str):
    try:
        files = [f for f in os.listdir(dirpath) if f.lower().endswith(f".{ext}")]
        files.sort()
        return files
    except Exception:
        return []


def render_generation_report(report: GenerationReport, *, strict: bool = False) -> None:
    """Affiche un rapport de génération dans l'UI Streamlit."""
    if report is None:
        return

    has_warning = report.has_warnings()
    if not report.ok and strict:
        st.error("Échec strict : des éléments requis sont manquants.")
    elif has_warning:
        st.warning("Génération terminée avec avertissements.")

    with st.expander("Rapport de génération", expanded=has_warning):
        if report.missing_tokens:
            st.write("**Tokens non remplacés**")
            st.write(", ".join(report.missing_tokens))
        if report.missing_shapes:
            st.write("**Shapes attendues non trouvées**")
            st.write(", ".join(report.missing_shapes))
        if report.missing_images:
            st.write("**Images non injectées / fallback**")
            st.write(", ".join(report.missing_images))
        if report.provider_warnings:
            st.write("**Avertissements provider/réseau**")
            for warn in report.provider_warnings:
                st.write(f"- {warn}")
        if report.notes:
            st.write("**Notes**")
            for note in report.notes:
                st.write(f"- {note}")
        if not has_warning and report.ok:
            st.caption("Rien à signaler.")


def render_template_validation(result: ValidationResult | None, *, strict: bool = False) -> None:
    if result is None:
        return
    status = result.severity
    if status == "KO":
        st.error("Validation du template : KO")
    elif status == "WARN":
        st.warning("Validation du template : avertissements")
    else:
        st.success("Validation du template : OK")

    st.write("**Checklist template**")
    st.write(f"- Tokens inconnus : {', '.join(result.unknown_tokens_in_template) if result.unknown_tokens_in_template else 'aucun'}")
    st.write(f"- Shapes manquantes : {', '.join(result.missing_required_shapes) if result.missing_required_shapes else 'aucune'}")
    if result.notes:
        for note in result.notes:
            st.caption(f"• {note}")
    if strict and status == "KO":
        st.error("Mode strict : génération bloquée tant que la validation est KO.")


def apply_pending_fields(
    state: MutableMapping[str, object],
    pending_key: str,
    target_keys: tuple[str, ...],
) -> bool:
    """
    Applique les valeurs en attente stockées dans `pending_key` sur `state` puis
    supprime la clé pending. Retourne True si quelque chose a été appliqué.
    """
    pending = state.get(pending_key)
    if not isinstance(pending, dict):
        return False
    for key in target_keys:
        if key in pending:
            state[key] = pending[key]
    state.pop(pending_key, None)
    return True
