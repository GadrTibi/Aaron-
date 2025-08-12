"""Streamlit view to generate the Guest Book PPTX."""

from __future__ import annotations

import os
import tempfile

import streamlit as st

from app.services.book_pdf import build_book_pdf
from app.services.book_tokens import build_book_mapping
from app.services.geocode import geocode_address
from app.services.map_image import build_static_map
from app.services.poi import fetch_transports, list_metro_lines, list_bus_lines
from app.services.pptx_fill import generate_book_pptx

from .utils import _sanitize_filename, list_templates


def render(config: dict) -> None:
    BOOK_TPL_DIR = config["BOOK_TPL_DIR"]
    OUT_DIR = config["OUT_DIR"]

    # ---- Template management ----
    st.subheader("Templates Book (PPTX)")
    st.caption(f"Dossier : {BOOK_TPL_DIR}")
    book_list = list_templates(BOOK_TPL_DIR, "pptx")
    uploaded_book = st.file_uploader(
        "Ajouter des templates PPTX (Book)",
        type=["pptx"],
        accept_multiple_files=True,
        key="up_book",
    )
    if uploaded_book:
        saved = 0
        for up in uploaded_book:
            safe_name = _sanitize_filename(up.name, "pptx")
            dst = os.path.join(BOOK_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name)
                i = 2
                while os.path.exists(os.path.join(BOOK_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(BOOK_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        book_list = list_templates(BOOK_TPL_DIR, "pptx")
    chosen_book = st.selectbox(
        "Choisir le template Book (PPTX)",
        options=book_list if book_list else ["(aucun)"]
    )

    def resolve_book_path(label: str | None) -> str | None:
        if not label or label == "(aucun)":
            return None
        return os.path.join(BOOK_TPL_DIR, label)

    # ---- Adresse & transports ----
    st.subheader("Adresse & transports (Slide 4)")
    addr_existing = st.session_state.get("bien_addr")
    if addr_existing:
        st.text_input("Adresse", addr_existing, key="bk_adresse", disabled=True)
    else:
        st.text_input("Adresse", st.session_state.get("bk_adresse", ""), key="bk_adresse")

    def _geocode_main_address():
        addr = st.session_state.get("bien_addr") or st.session_state.get("bk_adresse", "")
        if not addr:
            st.warning("Adresse introuvable…")
            return None, None
        with st.spinner("Recherche d'adresse…"):
            lat, lon = geocode_address(addr)
        if lat is None:
            st.warning("Adresse introuvable…")
        st.session_state["geo_lat"] = lat
        st.session_state["geo_lon"] = lon
        return lat, lon

    if st.button("Remplir transports automatiquement"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                radius = st.session_state.get("radius_m", 1200)
                tr = fetch_transports(lat, lon, radius_m=radius)
                metro = list_metro_lines(lat, lon, radius_m=radius)
                bus = list_bus_lines(lat, lon, radius_m=radius)
                st.session_state["q_tx"] = tr.get("taxi", "")
                st.session_state["metro_lines_auto"] = metro
                st.session_state["bus_lines_auto"] = bus
            except Exception as e:
                st.warning(f"Transports non chargés: {e}")
        else:
            st.session_state["q_tx"] = ""
            st.session_state["metro_lines_auto"] = []
            st.session_state["bus_lines_auto"] = []

    taxi_txt = st.session_state.get("q_tx", "")
    metro_auto = st.session_state.get("metro_lines_auto") or []
    bus_auto = st.session_state.get("bus_lines_auto") or []
    metro_refs = ", ".join([f"Ligne {x.get('ref')}" for x in metro_auto if x.get('ref')])
    bus_refs = ", ".join([f"Bus {x.get('ref')}" for x in bus_auto if x.get('ref')])
    st.write(f"Taxi : {taxi_txt or '—'}")
    st.write(f"Métro : {metro_refs or '—'}")
    st.write(f"Bus : {bus_refs or '—'}")

    # ---- Instructions (Slide 5) ----
    st.subheader("Instructions (Slide 5)")
    st.text_area("Porte d'entrée", key="bk_porte_entree_texte")
    st.text_area("Entrée", key="bk_entree_texte")
    st.text_area("Appartement", key="bk_appartement_texte")

    img_keys = ["book_img_porte", "book_img_entree", "book_img_appart"]
    imgs_exist = all(st.session_state.get(k) for k in img_keys)
    if imgs_exist:
        st.success("Images d'accès verrouillées ✅")
        if st.button("Réinitialiser"):
            for k in img_keys:
                st.session_state.pop(k, None)
            imgs_exist = False
    if not imgs_exist:
        up_porte = st.file_uploader("Photo porte", type=["jpg", "jpeg", "png"], key="up_book_img_porte")
        up_entree = st.file_uploader("Photo entrée", type=["jpg", "jpeg", "png"], key="up_book_img_entree")
        up_appart = st.file_uploader("Photo appartement", type=["jpg", "jpeg", "png"], key="up_book_img_appart")
        if st.button("Confirmer les images d'accès"):
            uploads = [up_porte, up_entree, up_appart]
            for up, key in zip(uploads, img_keys):
                if up is None:
                    st.session_state.pop(key, None)
                    continue
                fd, path = tempfile.mkstemp(suffix=os.path.splitext(up.name)[1])
                os.close(fd)
                with open(path, "wb") as f:
                    f.write(up.getbuffer())
                st.session_state[key] = path
            imgs_exist = all(st.session_state.get(k) for k in img_keys)
            if imgs_exist:
                st.success("Images d'accès enregistrées.")

    # ---- Wifi (Slide 8) ----
    st.subheader("Wifi (Slide 8)")
    st.text_input("Nom réseau", key="bk_network_name")
    st.text_input("Mot de passe", key="bk_network_password")

    # ---- Mapping construction ----
    base_mapping = build_book_mapping(st.session_state)
    extra_mapping = {
        "[[NB_SURFACE]]": f"{st.session_state.get('bien_surface', 0):.0f}",
        "[[NB_PIECES]]": f"{int(st.session_state.get('bien_pieces', 0))}",
        "[[NB_SDB]]": f"{int(st.session_state.get('bien_sdb', 0))}",
        "[[NB_COUCHAGES]]": f"{int(st.session_state.get('bien_couchages', 0))}",
        "[[MODE_CHAUFFAGE]]": st.session_state.get("bien_chauffage", ""),
    }
    mapping = {**base_mapping, **extra_mapping}

    image_by_shape: dict[str, str] = {}

    lat = st.session_state.get("geo_lat")
    lon = st.session_state.get("geo_lon")
    if lat and lon:
        map_path = build_static_map(lat, lon, pixel_radius=60, size=(900, 900))
        image_by_shape["MAP_BOOK_MASK"] = map_path
    if st.session_state.get("book_img_porte"):
        image_by_shape["PORTE_ENTREE_MASK"] = st.session_state["book_img_porte"]
    if st.session_state.get("book_img_entree"):
        image_by_shape["ENTREE_MASK"] = st.session_state["book_img_entree"]
    if st.session_state.get("book_img_appart"):
        image_by_shape["APPARTEMENT_MASK"] = st.session_state["book_img_appart"]

    # ---- Generation ----
    st.subheader("Générer le Book")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Générer le Book (PPTX)"):
            tpl = resolve_book_path(chosen_book)
            if not tpl or not os.path.exists(tpl):
                st.error("Aucun template Book PPTX sélectionné. Déposez/choisissez un template ci-dessus.")
                st.stop()
            pptx_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr', 'bien')}.pptx")
            generate_book_pptx(tpl, pptx_out, mapping, image_by_shape=image_by_shape or None)
            st.success(f"OK: {pptx_out}")
            with open(pptx_out, "rb") as f:
                st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))
    with col2:
        if st.button("Générer le Book (PDF simplifié)"):
            pdf_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr', 'bien')}.pdf")
            sections: list[str] = []
            build_book_pdf(
                pdf_out,
                "",
                "",
                sections,
            )
            st.success(f"OK: {pdf_out}")
            with open(pdf_out, "rb") as f:
                st.download_button("Télécharger le PDF", data=f.read(), file_name=os.path.basename(pdf_out))

