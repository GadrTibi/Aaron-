import os
from datetime import date
from pathlib import Path

import streamlit as st

from app.services.generation_report import GenerationReport
from app.services.mandat_templates import filter_mandat_templates
from app.services.mandat_tokens import build_mandat_mapping
from app.services.docx_fill import generate_docx_from_template
from app.services.template_catalog import (
    TemplateItem,
    list_effective_mandat_templates,
    list_repo_mandat_templates,
)
from app.services import template_roots
from app.services.token_utils import extract_docx_tokens
from app.services.token_audit import audit_template_tokens
from .utils import _sanitize_filename, render_generation_report


def render(config):
    TPL_DIR = config["TPL_DIR"]
    MANDAT_TPL_DIR = config["MANDAT_TPL_DIR"]
    OUT_DIR = config["OUT_DIR"]
    run_report = GenerationReport()

    # ---- Templates Mandat (DOCX) ----
    st.subheader("Templates Mandat (DOCX)")
    st.caption(f"Templates serveur (Git) : {template_roots.MANDAT_TPL_DIR}")

    def _select_template(mandat_type: str, select_key: str) -> TemplateItem | None:
        repo_items = list_repo_mandat_templates(mandat_type)
        filtered_repo = filter_mandat_templates(repo_items, mandat_type)
        options = filtered_repo or repo_items

        fallback_cd: list[TemplateItem] = []
        if not options and mandat_type == "MD":
            st.warning("Aucun template trouvé dans templates/mandat/md/. Ajoutez un .docx via Git.")
            fallback_cd = list_repo_mandat_templates("CD")
            filtered_cd = filter_mandat_templates(fallback_cd, "CD")
            fallback_cd = filtered_cd or fallback_cd
            if not fallback_cd:
                fallback_cd = list_effective_mandat_templates("CD")
                filtered_cd_effective = filter_mandat_templates(fallback_cd, "CD")
                fallback_cd = filtered_cd_effective or fallback_cd
        elif not options:
            st.warning("Aucun template trouvé dans templates/mandat/cd/. Ajoutez un .docx via Git.")

        if not options:
            options = list_effective_mandat_templates(mandat_type)
            filtered = filter_mandat_templates(options, mandat_type)
            if not filtered and options:
                st.warning("Aucun template filtré trouvé, affichage complet")
            options = filtered or options

        selected: TemplateItem | None = None
        if options:
            label = st.selectbox(
                "Templates serveur (Git)" if options[0].source == "repo" else "Templates hérités (MFY_* ou dossiers locaux)",
                options=[tpl.label for tpl in options],
                key=f"{select_key}_{mandat_type.lower()}",
            )
            selected = next((tpl for tpl in options if tpl.label == label), None)

        if not selected and fallback_cd:
            st.info("Templates Courte durée (CD) disponibles en secours.")
            label = st.selectbox(
                "Templates Courte durée (CD)",
                options=[tpl.label for tpl in fallback_cd],
                key=f"{select_key}_cd_fallback",
            )
            selected = next((tpl for tpl in fallback_cd if tpl.label == label), None)

        if not selected and not options and not fallback_cd:
            st.warning("Aucun template Mandat disponible. Ajoutez un .docx via Git ou via MFY_MAND_TPL_DIR.")

        return selected

    # ---- UI Mandat sans redondance ----
    st.subheader("Mandat (DOCX)")

    mandat_type_label = st.radio(
        "Type de mandat",
        options=["Courte durée (CD)", "Moyenne durée (MD)"],
        key="mandat_type_ui",
    )
    mandat_type = "MD" if "MD" in mandat_type_label else "CD"
    st.session_state["mandat_type"] = mandat_type_label

    selected_template = _select_template(mandat_type, select_key="mandat_tpl")

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

    st.date_input(
        "Date de signature",
        key="mandat_signature_date",
        value=st.session_state.get("mandat_signature_date", date.today()),
    )

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

    mapping = build_mandat_mapping(st.session_state, st.session_state.get("mandat_signature_date"))
    strict_default = bool(os.environ.get("MFY_STRICT_GENERATION"))
    strict_mode = st.checkbox(
        "Mode strict (bloquer si tokens manquants)",
        value=st.session_state.get("mandat_strict_mode", strict_default),
        key="mandat_strict_mode",
    )
    tpl_path = selected_template.path if selected_template else None

    template_tokens: set[str] = set()
    token_audit: dict | None = None
    if tpl_path and os.path.exists(tpl_path):
        try:
            template_tokens = extract_docx_tokens(tpl_path)
            token_audit = audit_template_tokens(template_tokens, mapping)
        except Exception as exc:
            st.warning(f"Validation du template Mandat impossible: {exc}")

    with st.expander("Validation du template (DOCX)", expanded=bool(template_tokens)):
        st.write(f"Tokens détectés dans le template : {len(template_tokens)}")
        if template_tokens:
            st.code(", ".join(sorted(template_tokens)))
        if token_audit:
            st.write(f"✅ Tokens OK : {len(token_audit['ok'])}")
            if token_audit["empty_values"]:
                st.warning(f"⚠️ Valeurs vides ({len(token_audit['empty_values'])}) : {', '.join(token_audit['empty_values'])}")
            else:
                st.caption("⚠️ Valeurs vides : aucune")
            if token_audit["missing_in_mapping"]:
                st.error(f"❌ Tokens non supportés ({len(token_audit['missing_in_mapping'])}) : {', '.join(token_audit['missing_in_mapping'])}")
            else:
                st.caption("❌ Tokens non supportés : aucun")
        elif tpl_path:
            st.caption("Impossible d'auditer ce template.")
        else:
            st.caption("Aucun template sélectionné.")

    disable_generate = strict_mode and token_audit is not None and (
        bool(token_audit["missing_in_mapping"]) or bool(token_audit["empty_values"])
    )
    if st.button("Générer le DOCX (Mandat)", disabled=disable_generate):
        tpl_path = selected_template.path if selected_template else None
        if not tpl_path or not os.path.exists(tpl_path):
            st.error(
                "Aucun template DOCX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus."
            )
            st.stop()
        if strict_mode and token_audit and (token_audit["missing_in_mapping"] or token_audit["empty_values"]):
            st.error("Mode strict : génération bloquée. Corrigez les tokens manquants ou les valeurs vides.")
            st.stop()
        out_path = os.path.join(
            OUT_DIR, f"Mandat - {st.session_state.get('bien_addr','bien')}.docx"
        )
        report = generate_docx_from_template(tpl_path, out_path, mapping, strict=strict_mode)
        report.merge(run_report)
        if strict_mode and not report.ok:
            st.error("Génération interrompue : le rapport signale des éléments bloquants.")
        else:
            st.success(f"OK : {out_path}")
            with open(out_path, "rb") as f:
                st.download_button(
                    "Télécharger le DOCX", data=f.read(), file_name=os.path.basename(out_path)
                )
        render_generation_report(report, strict=strict_mode)
