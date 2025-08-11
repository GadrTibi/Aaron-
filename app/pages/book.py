import os, tempfile
import streamlit as st

from app.services.pptx_fill import generate_estimation_pptx
from app.services.book_pdf import build_book_pdf

from .utils import _sanitize_filename, list_templates

def render(config):
    BOOK_TPL_DIR = config['BOOK_TPL_DIR']
    OUT_DIR = config['OUT_DIR']

    st.subheader("Templates Book (PPTX)")
    st.caption(f"Dossier : {BOOK_TPL_DIR}")
    book_list = list_templates(BOOK_TPL_DIR, "pptx")
    uploaded_book = st.file_uploader("Ajouter des templates PPTX (Book)", type=["pptx"], accept_multiple_files=True, key="up_book")
    if uploaded_book:
        saved = 0
        for up in uploaded_book:
            safe_name = _sanitize_filename(up.name, "pptx")
            dst = os.path.join(BOOK_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name); i = 2
                while os.path.exists(os.path.join(BOOK_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(BOOK_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        book_list = list_templates(BOOK_TPL_DIR, "pptx")
    chosen_book = st.selectbox("Choisir le template Book (PPTX)", options=book_list if book_list else ["(aucun)"])
    def resolve_book_path(label: str):
        if not label or label == "(aucun)":
            return None
        return os.path.join(BOOK_TPL_DIR, label)

    st.subheader("Contenu du Book")
    titre = st.text_input("Titre du book", st.session_state.get("bk_titre","Book - Présentation du bien"), key="bk_titre")
    intro_default = f"Adresse: {st.session_state.get('bien_addr','')}\nSurface: {st.session_state.get('bien_surface',0):.0f} m² - Pièces: {st.session_state.get('bien_pieces',0)} - Couchages: {st.session_state.get('bien_couchages',0)}\nPoints forts: (à détailler)\nPoints faibles: (à détailler)\n"
    intro = st.text_area("Intro", st.session_state.get("bk_intro", intro_default), key="bk_intro")

    st.markdown("**Photos (seront placées sur des shapes nommées BOOK_PHOTO_1..3 si présentes dans le template)**")
    photos = st.file_uploader("Importer jusqu'à 3 photos", type=["jpg","jpeg","png"], accept_multiple_files=True, key="bk_photos")

    book_mapping = {
        "[[BOOK_TITRE]]": st.session_state.get("bk_titre",""),
        "[[BOOK_INTRO]]": st.session_state.get("bk_intro",""),
        "[[ADRESSE]]": st.session_state.get("bien_addr",""),
        "[[NB_SURFACE]]": f"{st.session_state.get('bien_surface',0):.0f}",
        "[[NB_PIECES]]": f"{int(st.session_state.get('bien_pieces',0))}",
        "[[NB_SDB]]": f"{int(st.session_state.get('bien_sdb',0))}",
        "[[NB_COUCHAGES]]": f"{int(st.session_state.get('bien_couchages',0))}",
        "[[MODE_CHAUFFAGE]]": st.session_state.get("bien_chauffage",""),
    }

    image_by_shape = {}
    if photos:
        for idx, up in enumerate(photos[:3], start=1):
            fd, pth = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
            with open(pth, "wb") as f:
                f.write(up.getbuffer())
            image_by_shape[f"BOOK_PHOTO_{idx}"] = pth

    st.subheader("Générer le Book")
    colB1, colB2 = st.columns(2)
    with colB1:
        if st.button("Générer le Book (PPTX)"):
            tpl = resolve_book_path(chosen_book)
            if not tpl or not os.path.exists(tpl):
                st.error("Aucun template Book PPTX sélectionné. Déposez/choisissez un template ci-dessus.")
                st.stop()
            pptx_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr','bien')}.pptx")
            generate_estimation_pptx(tpl, pptx_out, book_mapping, chart_image=None, image_by_shape=image_by_shape or None)
            st.success(f"OK: {pptx_out}")
            with open(pptx_out, "rb") as f:
                st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))
    with colB2:
        if st.button("Générer le Book (PDF simplifié)"):
            pdf_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr','bien')}.pdf")
            sections = []
            build_book_pdf(pdf_out, st.session_state.get("bk_titre",""), st.session_state.get("bk_intro",""), sections)
            st.success(f"OK: {pdf_out}")
            with open(pdf_out, "rb") as f:
                st.download_button("Télécharger le PDF", data=f.read(), file_name=os.path.basename(pdf_out))
