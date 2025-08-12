"""Streamlit page to generate the Book PPTX."""
from __future__ import annotations

import os
import tempfile
import streamlit as st

from app.services.book_tokens import build_book_mapping
from app.services.map_image import build_static_map
from app.services.pptx_fill import generate_book_pptx
from app.views.utils import _sanitize_filename, list_templates


def render(config: dict) -> None:
    BOOK_TPL_DIR = config["BOOK_TPL_DIR"]
    OUT_DIR = config["OUT_DIR"]

    st.subheader("Template Book (PPTX)")
    st.caption(f"Dossier : {BOOK_TPL_DIR}")
    book_list = list_templates(BOOK_TPL_DIR, "pptx")
    uploaded_tpls = st.file_uploader(
        "Ajouter des templates PPTX (Book)",
        type=["pptx"],
        accept_multiple_files=True,
        key="up_book_tpl",
    )
    if uploaded_tpls:
        saved = 0
        for up in uploaded_tpls:
            safe = _sanitize_filename(up.name, "pptx")
            dst = os.path.join(BOOK_TPL_DIR, safe)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe)
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

    # ---- Informations ----
    st.subheader("Informations")
    addr_existing = st.session_state.get("bien_addr")
    if addr_existing:
        st.text_input("Adresse", addr_existing, key="bk_adresse", disabled=True)
    else:
        st.text_input("Adresse", st.session_state.get("bk_adresse", ""), key="bk_adresse")

    st.markdown("**Transports (depuis Estimation)**")
    taxi_txt = st.session_state.get("q_tx", "")
    metro_auto = st.session_state.get("metro_lines_auto") or []
    bus_auto = st.session_state.get("bus_lines_auto") or []
    metro_str = ", ".join([f"Ligne {x.get('ref')}" for x in metro_auto if x.get('ref')])
    bus_str = ", ".join([f"Bus {x.get('ref')}" for x in bus_auto if x.get('ref')])
    st.write(f"Taxi : {taxi_txt}")
    st.write(f"Métro : {metro_str}")
    st.write(f"Bus : {bus_str}")

    # ---- Instructions (Slide 5) ----
    st.subheader("Instructions (Slide 5)")
    st.text_area("Texte porte", key="bk_acc_porte_texte")
    st.text_area("Texte entrée", key="bk_acc_entree_texte")
    st.text_area("Texte appartement", key="bk_acc_appart_texte")

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

    # ---- Wifi ----
    st.subheader("Wifi (Slide 8)")
    st.text_input("Nom du réseau", key="bk_wifi_network")
    st.text_input("Mot de passe", key="bk_wifi_password")

    st.markdown("---")
    if st.button("Générer le BOOK (PPTX)"):
        tpl = resolve_book_path(chosen_book)
        if not tpl or not os.path.exists(tpl):
            st.error("Aucun template Book PPTX sélectionné. Déposez/choisissez un template ci-dessus.")
            st.stop()

        mapping = build_book_mapping(st.session_state)
        image_by_shape: dict[str, str] = {}

        lat = st.session_state.get("geo_lat")
        lon = st.session_state.get("geo_lon")
        if lat and lon:
            map_path = build_static_map(lat, lon, pixel_radius=60, size=(900, 900))
            image_by_shape["BOOK_MAP_MASK"] = map_path

        if st.session_state.get("book_img_porte"):
            image_by_shape["BOOK_ACCESS_PHOTO_PORTE"] = st.session_state["book_img_porte"]
        if st.session_state.get("book_img_entree"):
            image_by_shape["BOOK_ACCESS_PHOTO_ENTREE"] = st.session_state["book_img_entree"]
        if st.session_state.get("book_img_appart"):
            image_by_shape["BOOK_ACCESS_PHOTO_APPART"] = st.session_state["book_img_appart"]

        print("BOOK image_by_shape:", image_by_shape)
        out_path = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr','bien')}.pptx")
        generate_book_pptx(tpl, out_path, mapping, image_by_shape=image_by_shape)
        st.success(f"OK: {out_path}")
        with open(out_path, "rb") as f:
            st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(out_path))
