import os
import streamlit as st

from app.services.mandat_tokens import build_mandat_mapping
from app.services.docx_fill import generate_docx_from_template
from .utils import _sanitize_filename, list_templates


def render(config):
    TPL_DIR = config["TPL_DIR"]
    MANDAT_TPL_DIR = config["MANDAT_TPL_DIR"]
    OUT_DIR = config["OUT_DIR"]

    # ---- Templates Mandat (DOCX) ----
    st.subheader("Templates Mandat (DOCX)")
    st.caption(f"Dossier : {MANDAT_TPL_DIR}")
    man_list = list_templates(MANDAT_TPL_DIR, "docx")
    uploaded_docx = st.file_uploader(
        "Ajouter des templates DOCX", type=["docx"], accept_multiple_files=True, key="up_man"
    )
    if uploaded_docx:
        saved = 0
        for up in uploaded_docx:
            safe_name = _sanitize_filename(up.name, "docx")
            dst = os.path.join(MANDAT_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name)
                i = 2
                while os.path.exists(os.path.join(MANDAT_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(MANDAT_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        man_list = list_templates(MANDAT_TPL_DIR, "docx")
    legacy_man = os.path.join(TPL_DIR, "mandat_template.docx")
    has_legacy_man = os.path.exists(legacy_man)
    options = (["mandat_template.docx (héritage)"] if has_legacy_man else []) + man_list
    chosen_man = st.selectbox("Choisir le template Mandat", options=options if options else ["(aucun)"])

    def resolve_mandat_template_path(label: str):
        if not label or label == "(aucun)":
            return None
        if label == "mandat_template.docx (héritage)":
            return legacy_man
        return os.path.join(MANDAT_TPL_DIR, label)

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

    if st.button("Générer le DOCX (Mandat)"):
        tpl_path = resolve_mandat_template_path(chosen_man)
        if not tpl_path or not os.path.exists(tpl_path):
            st.error(
                "Aucun template DOCX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus."
            )
            st.stop()
        mapping = build_mandat_mapping(st.session_state)
        out_path = os.path.join(
            OUT_DIR, f"Mandat - {st.session_state.get('bien_addr','bien')}.docx"
        )
        generate_docx_from_template(tpl_path, out_path, mapping)
        st.success(f"OK : {out_path}")
        with open(out_path, "rb") as f:
            st.download_button(
                "Télécharger le DOCX", data=f.read(), file_name=os.path.basename(out_path)
            )
