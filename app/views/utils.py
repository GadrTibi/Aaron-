import os
import re
import streamlit as st

from app.services.generation_report import GenerationReport

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
