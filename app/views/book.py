"""Streamlit view to generate the Guest Book PPTX."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from app.services import template_roots
from app.services.book_pdf import build_book_pdf
from app.services.book_tokens import build_book_mapping
from app.services.generation_report import GenerationReport
from app.services.geocoding_fallback import geocode_address_fallback
from app.services.map_image import build_static_map
from app.services.poi import fetch_transports, list_metro_lines, list_bus_lines
from app.services.pptx_requirements import get_book_detectors, get_book_requirements
from app.services.pptx_fill import generate_book_pptx
from app.services.template_catalog import TemplateItem, list_effective_templates
from app.services.template_validation import validate_pptx_template
from app.services.token_aliases import apply_token_aliases

from .utils import (
    _sanitize_filename,
    render_generation_report,
    render_template_validation,
)


def _format_taxi_summary(items: list[dict]) -> str:
    if not items:
        return ""
    entry = items[0]
    name = entry.get("name") or "Station de taxi"
    distance = entry.get("distance_m")
    if distance is None:
        return name
    mins = int(round(distance / 80.0))
    return f"{name} ({distance} m – {mins} min)"


def _format_line_labels(items: list[dict], prefix: str) -> str:
    labels: list[str] = []
    for item in items:
        ref = item.get("ref") or item.get("name")
        if not ref:
            continue
        labels.append(f"{prefix} {ref}" if prefix else str(ref))
    return ", ".join(labels)


def _display_transport_caption(*debug_values: dict | None) -> None:
    pairs = [(label, dbg) for label, dbg in zip(["taxi", "metro", "bus"], debug_values) if isinstance(dbg, dict)]
    if not pairs:
        return
    mirror = None
    parts: list[str] = []
    for label, dbg in pairs:
        if not mirror and dbg.get("mirror"):
            mirror = dbg.get("mirror")
        segment: list[str] = [label]
        if dbg.get("duration_ms") is not None:
            segment.append(f"{int(dbg['duration_ms'])}ms")
        if dbg.get("items") is not None:
            segment.append(f"{int(dbg['items'])} items")
        status = dbg.get("status")
        if status and status != "ok":
            segment.append(status)
        parts.append(" ".join(segment))
    caption_parts: list[str] = []
    if mirror:
        caption_parts.append(f"mirror={mirror}")
    caption_parts.extend(parts)
    try:
        st.caption("Transports: " + " | ".join(caption_parts))
    except Exception:
        pass


def render(config: dict) -> None:
    BOOK_TPL_DIR = config["BOOK_TPL_DIR"]
    OUT_DIR = config["OUT_DIR"]
    run_report = GenerationReport()

    # ---- Template management ----
    st.subheader("Templates Book (PPTX)")
    st.caption(f"Templates serveur (Git) : {template_roots.BOOK_TPL_DIR}")

    def _select_template(select_key: str) -> TemplateItem | None:
        effective = list_effective_templates("book")
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
            st.warning("Aucun template trouvé dans templates/book. Ajoutez-en via Git.")
            if legacy_items:
                label = st.selectbox(
                    "Templates hérités (MFY_* ou dossiers locaux)",
                    options=[tpl.label for tpl in legacy_items],
                    key=f"{select_key}_legacy",
                )
                selected = next((tpl for tpl in legacy_items if tpl.label == label), None)
        return selected

    selected_template = _select_template("book_tpl")

    with st.expander("Template uploadé (non persistant)", expanded=False):
        st.caption("Les fichiers déposés ici ne sont pas persistants sur Streamlit Community Cloud.")
        uploaded_book = st.file_uploader(
            "Ajouter des templates PPTX (Book)",
            type=["pptx"],
            accept_multiple_files=True,
            key="up_book",
        )
        book_upload_dir = Path(BOOK_TPL_DIR)
        if uploaded_book:
            book_upload_dir.mkdir(parents=True, exist_ok=True)
            saved = 0
            for up in uploaded_book:
                safe_name = _sanitize_filename(up.name, "pptx")
                dst = book_upload_dir / safe_name
                if dst.exists():
                    base = dst.stem
                    ext = dst.suffix
                    i = 2
                    candidate = book_upload_dir / f"{base} ({i}){ext}"
                    while candidate.exists():
                        i += 1
                        candidate = book_upload_dir / f"{base} ({i}){ext}"
                    dst = candidate
                with open(dst, "wb") as f:
                    f.write(up.getbuffer())
                saved += 1
            st.success(f"{saved} template(s) ajouté(s).")
            st.toast("Rafraîchissez la sélection ci-dessus pour utiliser les templates ajoutés.")

        upload_items: list[TemplateItem] = []
        if book_upload_dir.resolve() != template_roots.BOOK_TPL_DIR.resolve():
            upload_items = [
                TemplateItem(label=p.name, source="uploaded", path=p)
                for p in book_upload_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".pptx"
            ]
        if upload_items:
            use_uploaded = st.checkbox(
                "Utiliser un template uploadé (non persistant)",
                key="use_book_uploaded",
            )
            if use_uploaded:
                label = st.selectbox(
                    "Templates uploadés",
                    options=[tpl.label for tpl in upload_items],
                    key="book_uploaded_select",
                )
                selected_template = next((tpl for tpl in upload_items if tpl.label == label), selected_template)

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
            return None, None, ""
        with st.spinner("Recherche d'adresse…"):
            try:
                lat, lon, provider_used = geocode_address_fallback(addr, report=run_report)
            except ValueError as exc:
                st.error(str(exc))
                return None, None, ""
        if lat is None:
            if run_report.provider_warnings:
                st.error(run_report.provider_warnings[-1])
            else:
                st.warning("Adresse introuvable…")
        elif provider_used and provider_used != "Nominatim":
            st.warning(f"Fallback géocodage: {provider_used} utilisé.")
        st.session_state["geo_lat"] = lat
        st.session_state["geo_lon"] = lon
        return lat, lon, provider_used

    if st.button("Remplir transports automatiquement"):
        lat, lon, _ = _geocode_main_address()
        if lat is not None:
            try:
                radius = st.session_state.get("radius_m", 1200)
                taxi_items, taxi_debug = fetch_transports(lat, lon, radius_m=radius)
                metro_items, metro_debug = list_metro_lines(lat, lon, radius_m=radius)
                bus_items, bus_debug = list_bus_lines(lat, lon, radius_m=radius)
                st.session_state["q_tx"] = _format_taxi_summary(taxi_items)
                st.session_state["metro_lines_auto"] = metro_items
                st.session_state["bus_lines_auto"] = bus_items
                _display_transport_caption(taxi_debug, metro_debug, bus_debug)
            except Exception as e:
                st.warning(f"Transports non chargés: {e}")
        else:
            st.session_state["q_tx"] = ""
            st.session_state["metro_lines_auto"] = []
            st.session_state["bus_lines_auto"] = []

    taxi_txt = st.session_state.get("q_tx", "")
    metro_auto = st.session_state.get("metro_lines_auto") or []
    bus_auto = st.session_state.get("bus_lines_auto") or []
    metro_refs = _format_line_labels(metro_auto, "")
    bus_refs = _format_line_labels(bus_auto, "")
    st.write(f"Taxi : {taxi_txt or '—'}")
    st.write(f"Stations proches : {metro_refs or '—'}")
    st.write(f"Arrêts de bus proches : {bus_refs or '—'}")

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

    mapping_keys_before_aliases = set(mapping.keys())
    mapping = apply_token_aliases(mapping)
    applied_aliases = sorted(k for k in mapping if k not in mapping_keys_before_aliases)

    with st.expander("Debug mapping injection", expanded=False):
        alias_label = ", ".join(applied_aliases) if applied_aliases else "aucun"
        st.caption(f"Aliases appliqués: {alias_label}")
        st.json(mapping)

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

    strict_mode = bool(os.environ.get("MFY_STRICT_GENERATION"))
    tpl_for_validation = selected_template.path if selected_template else None
    validation_result = None
    if tpl_for_validation and os.path.exists(tpl_for_validation):
        try:
            validation_result = validate_pptx_template(
                tpl_for_validation,
                set(mapping.keys()),
                get_book_requirements(),
                requirement_detectors=get_book_detectors(),
            )
        except Exception as exc:
            st.warning(f"Validation du template Book impossible: {exc}")
    render_template_validation(validation_result, strict=strict_mode)

    # ---- Generation ----
    st.subheader("Générer le Book")
    col1, col2 = st.columns(2)
    with col1:
        disable_generate = strict_mode and validation_result is not None and validation_result.severity == "KO"
        if st.button("Générer le Book (PPTX)", disabled=disable_generate):
            tpl = selected_template.path if selected_template else None
            if not tpl or not os.path.exists(tpl):
                st.error("Aucun template Book PPTX sélectionné. Déposez/choisissez un template ci-dessus.")
                st.stop()
            pptx_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr', 'bien')}.pptx")
            report = generate_book_pptx(tpl, pptx_out, mapping, image_by_shape=image_by_shape or None, strict=strict_mode)
            if validation_result and validation_result.notes:
                for note in validation_result.notes:
                    report.add_note(note)
            report.merge(run_report)
            if strict_mode and validation_result and validation_result.severity == "KO":
                st.error("Génération bloquée : le template n'est pas valide en mode strict.")
            elif strict_mode and not report.ok:
                st.error("Génération interrompue : le rapport signale des éléments bloquants.")
            else:
                st.success(f"OK: {pptx_out}")
                with open(pptx_out, "rb") as f:
                    st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))
            render_generation_report(report, strict=strict_mode)
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
