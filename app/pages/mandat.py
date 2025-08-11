import os
from datetime import datetime
import streamlit as st

from app.services.docx_fill import replace_placeholders_docx

from .utils import _sanitize_filename, list_templates

def render(config):
    TPL_DIR = config['TPL_DIR']
    MAN_TPL_DIR = config['MAN_TPL_DIR']
    OUT_DIR = config['OUT_DIR']

    st.subheader("Templates Mandat (DOCX)")
    st.caption(f"Dossier : {MAN_TPL_DIR}")
    man_list = list_templates(MAN_TPL_DIR, "docx")
    uploaded_docx = st.file_uploader("Ajouter des templates DOCX", type=["docx"], accept_multiple_files=True, key="up_man")
    if uploaded_docx:
        saved = 0
        for up in uploaded_docx:
            safe_name = _sanitize_filename(up.name, "docx")
            dst = os.path.join(MAN_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name); i = 2
                while os.path.exists(os.path.join(MAN_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(MAN_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        man_list = list_templates(MAN_TPL_DIR, "docx")
    legacy_man = os.path.join(TPL_DIR, "mandat_template.docx")
    has_legacy_man = os.path.exists(legacy_man)
    options = (["mandat_template.docx (héritage)"] if has_legacy_man else []) + man_list
    chosen_man = st.selectbox("Choisir le template Mandat", options=options if options else ["(aucun)"])
    def resolve_man_path(label: str):
        if not label or label == "(aucun)":
            return None
        if label == "mandat_template.docx (héritage)":
            return legacy_man
        return os.path.join(MAN_TPL_DIR, label)

    st.subheader("Champs spécifiques Mandat")
    date_debut = st.date_input("Date de début de mandat", datetime.today(), key="man_date")
    mode_eau_chaude = st.text_input("Mode de production d'eau chaude", "Ballon électrique", key="man_eau")

    mandat_map = {
        "«Forme_du_propriétaire»": st.session_state.get("own_forme",""),
        "«Nom_du_propriétaire»": st.session_state.get("own_nom",""),
        "«Prénom_du_propriétaire»": st.session_state.get("own_prenom",""),
        "«Adresse_du_propriétaire»": st.session_state.get("own_addr",""),
        "«Code_postal_du_propriétaire»": st.session_state.get("own_cp",""),
        "«Ville_du_propriétaire»": st.session_state.get("own_ville",""),
        "«Adresse_du_bien_loué»": st.session_state.get("bien_addr",""),
        "«Surface_totale_du_bien»": str(int(st.session_state.get("bien_surface",0))),
        "«Nombre_de_pièces_du_bien»": str(int(st.session_state.get("bien_pieces",0))),
        "«Nombre_de_pax»": str(int(st.session_state.get("bien_couchages",0))),
        "«Mode_de_production_de_chauffage»": st.session_state.get("bien_chauffage",""),
        "«Mode_de_production_deau_chaude_sanitair»": mode_eau_chaude,
        "«Mail_du_propriétaire»": st.session_state.get("own_email",""),
        "«Date_de_début_de_mandat»": date_debut.strftime("%d/%m/%Y"),
    }

    st.subheader("Générer le Mandat (DOCX)")
    man_tpl_path = resolve_man_path(chosen_man)
    if st.button("Générer le DOCX (Mandat)"):
        if not man_tpl_path or not os.path.exists(man_tpl_path):
            st.error("Aucun template DOCX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus.")
            st.stop()
        docx_out = os.path.join(OUT_DIR, f"Mandat - {st.session_state.get('own_nom','client')}.docx")
        replace_placeholders_docx(man_tpl_path, docx_out, mandat_map)
        st.success(f"OK: {docx_out}")
        with open(docx_out, "rb") as f:
            st.download_button("Télécharger le DOCX", data=f.read(), file_name=os.path.basename(docx_out))

