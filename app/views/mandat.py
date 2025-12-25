import os
from datetime import date
from pathlib import Path

import streamlit as st

from app.services.generation_report import GenerationReport
from app.services.mandat_tokens import build_mandat_mapping
from app.services.docx_fill import generate_docx_from_template
from app.services.template_catalog import TemplateItem, list_effective_templates
from app.services import template_roots
from app.services.template_validation import validate_docx_template
from .utils import _sanitize_filename, render_generation_report, render_template_validation


def render(config):
    TPL_DIR = config["TPL_DIR"]
    MANDAT_TPL_DIR = config["MANDAT_TPL_DIR"]
    OUT_DIR = config["OUT_DIR"]
    run_report = GenerationReport()

    # ---- Templates Mandat (DOCX) ----
    st.subheader("Templates Mandat (DOCX)")
    st.caption(f"Templates serveur (Git) : {template_roots.MANDAT_TPL_DIR}")

    def _select_template(kind: str, select_key: str) -> TemplateItem | None:
        effective = list_effective_templates(kind)
        repo_items = [tpl for tpl in effective if tpl.source == "repo"]
        legacy_items = [tpl for tpl in effective if tpl.source != "repo"]
        selected: TemplateItem | None = None

        if repo_items:
            label = st.selectbox(
                "Templates serveur (Git)",
                options=[tpl.label for tpl in repo_items],
                key=f"{select_key}_repo",
            )
            selected = next((tpl for tpl in repo_items if tpl.label == label), None)
        else:
            st.warning("Aucun template trouvé dans templates/mandat. Ajoutez-en via Git.")
            if legacy_items:
                label = st.selectbox(
                    "Templates hérités (MFY_* ou dossiers locaux)",
                    options=[tpl.label for tpl in legacy_items],
                    key=f"{select_key}_legacy",
                )
                selected = next((tpl for tpl in legacy_items if tpl.label == label), None)
        return selected

    selected_template = _select_template("mandat", select_key="mandat_tpl")

    with st.expander("Template uploadé (non persistant)", expanded=False):
        st.caption("Les fichiers déposés ici ne sont pas persistants sur Streamlit Community Cloud.")
        uploaded_docx = st.file_uploader(
            "Ajouter des templates DOCX",
            type=["docx"],
            accept_multiple_files=True,
            key="up_man",
        )
        man_upload_dir = Path(MANDAT_TPL_DIR)
        if uploaded_docx:
            man_upload_dir.mkdir(parents=True, exist_ok=True)
            saved = 0
            for up in uploaded_docx:
                safe_name = _sanitize_filename(up.name, "docx")
                dst = man_upload_dir / safe_name
                if dst.exists():
                    base = dst.stem
                    ext = dst.suffix
                    i = 2
                    candidate = man_upload_dir / f"{base} ({i}){ext}"
                    while candidate.exists():
                        i += 1
                        candidate = man_upload_dir / f"{base} ({i}){ext}"
                    dst = candidate
                with open(dst, "wb") as f:
                    f.write(up.getbuffer())
                saved += 1
            st.success(f"{saved} template(s) ajouté(s).")
            st.toast("Rafraîchissez la sélection ci-dessus pour utiliser les templates ajoutés.")

        upload_items: list[TemplateItem] = []
        if man_upload_dir.resolve() != template_roots.MANDAT_TPL_DIR.resolve():
            upload_items = [
                TemplateItem(label=p.name, source="uploaded", path=p)
                for p in man_upload_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".docx"
            ]
        if upload_items:
            use_uploaded = st.checkbox(
                "Utiliser un template uploadé (non persistant)",
                key="use_man_uploaded",
            )
            if use_uploaded:
                label = st.selectbox(
                    "Templates uploadés",
                    options=[tpl.label for tpl in upload_items],
                    key="mandat_uploaded_select",
                )
                selected_template = next((tpl for tpl in upload_items if tpl.label == label), selected_template)

    # ---- UI Mandat sans redondance ----
    st.subheader("Mandat (DOCX)")

    st.caption(f"Adresse bien : {st.session_state.get('bien_addr','')}")
    st.caption(
        f"Surface : {st.session_state.get('bien_surface','')} m² • Pièces : {st.session_state.get('bien_pieces','')} • SDB : {st.session_state.get('bien_sdb','')} • Couchages : {st.session_state.get('bien_couchages','')}"
    )
    st.caption(
        f"Chauffage : {st.session_state.get('bien_chauffage','')} • Eau chaude : {st.session_state.get('bien_eau_chaude', st.session_state.get('bien_eau_chaude_mode',''))}"
    )

    colA, colB = st.columns(2)
    with colA:
        st.text_input(
            "Type de pièces d'eau",
            key="mandat_type_pieces_eau",
            value=st.session_state.get("mandat_type_pieces_eau", "Salle(s) d’eau"),
        )
        st.checkbox(
            "Animaux autorisés",
            key="mandat_animaux_autorises",
            value=st.session_state.get("mandat_animaux_autorises", False),
        )
        st.number_input(
            "Commission MFY (%)",
            0,
            100,
            value=int(st.session_state.get("mandat_commission_pct", st.session_state.get("rn_comm", 20))),
            key="mandat_commission_pct",
        )
    with colB:
        st.date_input("Date de début de mandat", key="mandat_date_debut")

        # Date de signature : par défaut aujourd'hui, stockée dans le session_state + formats prêts pour le DOCX
        default_sig_date = st.session_state.get("mandat_signature_date", date.today()) or date.today()
        sig_date = st.date_input(
            "Date de signature du mandat",
            key="mandat_signature_date",
            value=default_sig_date,
        )
        if not sig_date:
            sig_date = date.today()
            st.session_state["mandat_signature_date"] = sig_date
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        st.session_state["mandat_jour_signature_str"] = jours[sig_date.weekday()]
        st.session_state["mandat_date_signature_str"] = sig_date.strftime("%d/%m/%Y")

    st.text_area("Destination du bien (texte)", key="mandat_destination_bien")
    st.text_area("Remise de pièces (liste/texte)", key="mandat_remise_pieces")

    if not (st.session_state.get("owner_nom") or st.session_state.get("own_nom")):
        st.markdown("**Propriétaire (si non saisi ailleurs)**")
        st.text_input("Forme du propriétaire", key="owner_forme")
        st.text_input("Nom", key="owner_nom")
        st.text_input("Prénom", key="owner_prenom")
        st.text_input("Adresse", key="owner_adresse")
        st.text_input("Code postal", key="owner_cp")
        st.text_input("Ville", key="owner_ville")
        st.text_input("Email", key="owner_email")

    mapping = build_mandat_mapping(st.session_state)
    strict_mode = bool(os.environ.get("MFY_STRICT_GENERATION"))
    tpl_path = selected_template.path if selected_template else None
    validation_result = None
    if tpl_path and os.path.exists(tpl_path):
        try:
            validation_result = validate_docx_template(tpl_path, set(mapping.keys()))
        except Exception as exc:
            st.warning(f"Validation du template Mandat impossible: {exc}")
    render_template_validation(validation_result, strict=strict_mode)

    disable_generate = strict_mode and validation_result is not None and validation_result.severity == "KO"
    if st.button("Générer le DOCX (Mandat)", disabled=disable_generate):
        tpl_path = selected_template.path if selected_template else None
        if not tpl_path or not os.path.exists(tpl_path):
            st.error(
                "Aucun template DOCX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus."
            )
            st.stop()
        out_path = os.path.join(
            OUT_DIR, f"Mandat - {st.session_state.get('bien_addr','bien')}.docx"
        )
        report = generate_docx_from_template(tpl_path, out_path, mapping, strict=strict_mode)
        if validation_result and validation_result.notes:
            for note in validation_result.notes:
                report.add_note(note)
        report.merge(run_report)
        if strict_mode and validation_result and validation_result.severity == "KO":
            st.error("Génération bloquée : le template n'est pas valide en mode strict.")
        elif strict_mode and not report.ok:
            st.error("Génération interrompue : le rapport signale des éléments bloquants.")
        else:
            st.success(f"OK : {out_path}")
            with open(out_path, "rb") as f:
                st.download_button(
                    "Télécharger le DOCX", data=f.read(), file_name=os.path.basename(out_path)
                )
        render_generation_report(report, strict=strict_mode)
