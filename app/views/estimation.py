import os
import re
import streamlit as st

from app.services.revenue import RevenueInputs, compute_revenue
from app.services.plots import build_estimation_histo
from app.services.pptx_fill import generate_estimation_pptx
from app.services.poi import (
    fetch_transports,
    list_incontournables,
    list_spots,
    list_visites,
    list_metro_lines,
    list_bus_lines,
)
from app.services.geocode import geocode_address
from app.services.image_fetcher import get_poi_image, NO_IMAGE_PLACEHOLDER
from app.services.map_image import build_static_map

from .utils import _sanitize_filename, list_templates


def _resolve_base_nightly_price() -> float:
    keys = [
        "base_nightly_price",
        "price_per_night",
        "base_price",
        "price_base",
        "rn_prix",
    ]
    for key in keys:
        if key in st.session_state:
            raw = st.session_state.get(key)
            if raw in (None, ""):
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    raise ValueError("Paramètre 'base_nightly_price' introuvable dans l'état de l'application.")


def _guess_city_country(address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    parts = [part.strip() for part in re.split(r"[\n,]", address) if part.strip()]
    if len(parts) >= 2:
        city = parts[-2]
        country = parts[-1]
    elif parts:
        city = parts[-1]
        country = None
    else:
        city = country = None
    return (city or None, country or None)


def render(config):
    TPL_DIR = config['TPL_DIR']
    EST_TPL_DIR = config['EST_TPL_DIR']
    OUT_DIR = config['OUT_DIR']

    # ---------- APPLY PENDING PREFILL BEFORE WIDGETS ----------
    if "__prefill" in st.session_state and isinstance(st.session_state["__prefill"], dict):
        # apply and pop so we don't loop
        for k, v in st.session_state["__prefill"].items():
            st.session_state[k] = v
        st.session_state.pop("__prefill", None)

    for legacy_key in ("visite1_imgs", "visite2_imgs", "visite1_choice", "visite2_choice", "visites_locked"):
        if legacy_key in st.session_state:
            st.session_state.pop(legacy_key, None)

    # ---- Templates Estimation (PPTX) ----
    st.subheader("Templates Estimation (PPTX)")
    st.caption(f"Dossier : {EST_TPL_DIR}")
    est_list = list_templates(EST_TPL_DIR, "pptx")
    uploaded_tpls = st.file_uploader("Ajouter des templates PPTX", type=["pptx"], accept_multiple_files=True, key="up_est")
    if uploaded_tpls:
        saved = 0
        for up in uploaded_tpls:
            safe_name = _sanitize_filename(up.name, "pptx")
            dst = os.path.join(EST_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name); i = 2
                while os.path.exists(os.path.join(EST_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(EST_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        est_list = list_templates(EST_TPL_DIR, "pptx")
    legacy_est = os.path.join(TPL_DIR, "estimation_template.pptx")
    has_legacy_est = os.path.exists(legacy_est)
    options = (["estimation_template.pptx (héritage)"] if has_legacy_est else []) + est_list
    chosen_est = st.selectbox("Choisir le template Estimation", options=options if options else ["(aucun)"])
    def resolve_est_path(label: str):
        if not label or label == "(aucun)":
            return None
        if label == "estimation_template.pptx (héritage)":
            return legacy_est
        return os.path.join(EST_TPL_DIR, label)

    def _geocode_main_address():
        addr = st.session_state.get("bien_addr", "")
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

    # ---- Quartier & transports (Slide 4) ----
    st.subheader("Quartier (Slide 4)")
    quartier_texte = st.text_area("Texte d'intro du quartier (paragraphe)", st.session_state.get("q_txt", "Texte libre saisi par l'utilisateur."), key="q_txt")
    if st.button("Remplir Transports (auto)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                radius = st.session_state.get("radius_m", 1200)
                tr = fetch_transports(lat, lon, radius_m=radius)
                metro = list_metro_lines(lat, lon, radius_m=radius)
                bus = list_bus_lines(lat, lon, radius_m=radius)
                st.session_state["q_tx"] = tr.get("taxi", "")
                st.session_state['metro_lines_auto'] = metro
                st.session_state['bus_lines_auto'] = bus
            except Exception as e:
                st.warning(f"Transports non chargés: {e}")
        else:
            st.session_state["q_tx"] = ""
            st.session_state['metro_lines_auto'] = []
            st.session_state['bus_lines_auto'] = []
    taxi_txt = st.session_state.get("q_tx", "")
    metro_auto = st.session_state.get('metro_lines_auto', [])
    bus_auto = st.session_state.get('bus_lines_auto', [])
    metro_refs = ", ".join([f"Ligne {x.get('ref')}" for x in metro_auto if x.get('ref')])
    bus_refs = ", ".join([f"Bus {x.get('ref')}" for x in bus_auto if x.get('ref')])
    st.write(f"Taxi : {taxi_txt or '—'}")
    st.write(f"Métro : {metro_refs or '—'}")
    st.write(f"Bus : {bus_refs or '—'}")

    # ---- Incontournables (3), Spots (2), Visites (2 + images) ----
    st.subheader("Adresses du quartier (Slide 4)")
    if st.button("Charger Incontournables (≈15)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                st.session_state['incontournables_list'] = list_incontournables(
                    lat, lon, radius_m=st.session_state.get("radius_m", 1200)
                )
            except Exception as e:
                st.warning(f"Incontournables non chargés: {e}")
    inco_list = st.session_state.get('incontournables_list', [])
    default_inco = [x for x in [st.session_state.get('i1'), st.session_state.get('i2'), st.session_state.get('i3')] if x]
    sel_inco = st.multiselect(
        "Incontournables (max 3)",
        options=inco_list,
        default=default_inco or inco_list[:3]
    )
    sel_inco = sel_inco[:3]
    st.session_state['i1'] = sel_inco[0] if len(sel_inco) > 0 else ""
    st.session_state['i2'] = sel_inco[1] if len(sel_inco) > 1 else ""
    st.session_state['i3'] = sel_inco[2] if len(sel_inco) > 2 else ""

    if st.button("Charger Spots (≈10)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                st.session_state['spots_list'] = list_spots(
                    lat, lon, radius_m=st.session_state.get("radius_m", 1200)
                )
            except Exception as e:
                st.warning(f"Spots non chargés: {e}")
    spots_list = st.session_state.get('spots_list', [])
    default_spots = [x for x in [st.session_state.get('s1'), st.session_state.get('s2')] if x]
    sel_spots = st.multiselect(
        "Spots (max 2)",
        options=spots_list,
        default=default_spots or spots_list[:2]
    )
    sel_spots = sel_spots[:2]
    st.session_state['s1'] = sel_spots[0] if len(sel_spots) > 0 else ""
    st.session_state['s2'] = sel_spots[1] if len(sel_spots) > 1 else ""

    st.markdown("**Lieux à visiter (2) — images auto (Wikipedia/Commons)**")
    if st.button("Charger Visites (≈10)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                st.session_state['visites_list'] = list_visites(
                    lat, lon, radius_m=st.session_state.get("radius_m", 1200)
                )
            except Exception as e:
                st.warning(f"Visites non chargées: {e}")
    vis_list = st.session_state.get('visites_list', [])
    default_vis = [x for x in [st.session_state.get('v1'), st.session_state.get('v2')] if x]
    sel_vis = st.multiselect(
        "Lieux à visiter (max 2)",
        options=vis_list,
        default=default_vis or vis_list[:2]
    )
    sel_vis = sel_vis[:2]
    st.session_state['v1'] = sel_vis[0] if len(sel_vis) > 0 else ""
    st.session_state['v2'] = sel_vis[1] if len(sel_vis) > 1 else ""

    address = st.session_state.get("bien_addr", "")
    city_hint, country_hint = _guess_city_country(address)

    refresh_images = st.button("Rafraîchir les images des visites")

    def _update_poi_image(slot: str, poi_label: str | None, force: bool = False) -> None:
        path_key = f"{slot}_img_path"
        query_key = f"{slot}_img_query"
        if not poi_label:
            st.session_state.pop(path_key, None)
            st.session_state.pop(query_key, None)
            return
        if force:
            st.session_state.pop(query_key, None)
        query = " ".join(part for part in [poi_label, city_hint, country_hint] if part)
        if st.session_state.get(query_key) == query and st.session_state.get(path_key):
            return
        image_path = get_poi_image(poi_label, city_hint, country_hint)
        st.session_state[path_key] = image_path
        st.session_state[query_key] = query

    _update_poi_image("visite1", st.session_state.get('v1'), refresh_images)
    _update_poi_image("visite2", st.session_state.get('v2'), refresh_images)

    def _render_poi_preview(title: str, poi_label: str | None, path_key: str) -> None:
        st.write(f"**{title}**")
        if not poi_label:
            st.caption("Sélectionnez un lieu pour générer automatiquement son image.")
            return
        st.caption(poi_label)
        image_path = st.session_state.get(path_key)
        if image_path and os.path.exists(image_path) and image_path != NO_IMAGE_PLACEHOLDER:
            st.image(image_path, use_column_width=True)
        else:
            st.markdown("🖼️ **Image non disponible**")
            st.caption("Image non disponible")

    col_img1, col_img2 = st.columns(2)
    with col_img1:
        _render_poi_preview("Visite 1", st.session_state.get('v1'), 'visite1_img_path')
    with col_img2:
        _render_poi_preview("Visite 2", st.session_state.get('v2'), 'visite2_img_path')

    st.slider("Rayon (m)", min_value=300, max_value=3000, value=st.session_state.get("radius_m", 1200), step=100, key="radius_m")

    # Points forts & Challenges (Slide 5)
    st.subheader("Points forts & Challenges (Slide 5)")
    colPF, colCH = st.columns(2)
    with colPF:
        point_fort_1 = st.text_input("Point fort 1", st.session_state.get("pf1", "Proche des transports"), key="pf1")
        point_fort_2 = st.text_input("Point fort 2", st.session_state.get("pf2", "Récemment rénové"), key="pf2")
    with colCH:
        challenge_1 = st.text_input("Challenge 1", st.session_state.get("ch1", "Pas d’ascenseur"), key="ch1")
        challenge_2 = st.text_input("Challenge 2", st.session_state.get("ch2", "Bruit de la rue en journée"), key="ch2")

    # ---- Revenus + scénarios ----
    st.subheader("Paramètres revenus")
    colA, colB, colC, colD = st.columns(4)
    with colA:
        prix_nuitee = st.number_input("Prix par nuitée (€)", min_value=0.0, value=120.0, step=5.0, key="rn_prix")
    with colB:
        taux_occupation = st.slider("Taux d'occupation (%)", min_value=0, max_value=100, value=70, step=1, key="rn_occ")
    with colC:
        commission_mfy = st.slider("Commission MFY (%)", min_value=0, max_value=50, value=20, step=1, key="rn_comm")
    with colD:
        frais_menage = st.number_input("Frais de ménage (mensuels, €)", min_value=0.0, value=0.0, step=5.0, key="rn_menage")

    st.markdown("**Scénarios de prix (nuitée)**")
    c1, c2, c3 = st.columns(3)
    with c1:
        coef_pess = st.number_input("Coef pessimiste", min_value=0.5, max_value=2.0, value=0.90, step=0.05, key="sc_p")
    with c2:
        coef_cible = st.number_input("Coef cible", min_value=0.5, max_value=2.0, value=1.00, step=0.05, key="sc_c")
    with c3:
        coef_opt = st.number_input("Coef optimiste", min_value=0.5, max_value=2.0, value=1.10, step=0.05, key="sc_o")

    calc = compute_revenue(RevenueInputs(
        prix_nuitee=float(prix_nuitee),
        taux_occupation_pct=float(taux_occupation),
        commission_pct=float(commission_mfy),
        frais_menage_mensuels=float(frais_menage),
    ))

    REV_BRUT = calc["revenu_brut"]
    FRAIS_GEN = calc["frais_generaux"]
    REV_NET  = calc["revenu_net"]
    JOURS_OCC = calc["jours_occupes"]

    st.metric("Jours loués / mois", f"{JOURS_OCC:.1f} j")
    colX, colY, colZ = st.columns(3)
    colX.metric("Revenu brut", f"{REV_BRUT:.0f} €")
    colY.metric("Frais généraux", f"{FRAIS_GEN:.0f} €")
    colZ.metric("Revenu net", f"{REV_NET:.0f} €")

    # Scénarios prix
    PRIX_PESS = prix_nuitee * coef_pess
    PRIX_CIBLE = prix_nuitee * coef_cible
    PRIX_OPT = prix_nuitee * coef_opt

    st.markdown("**Évo du prix/nuitée**")
    histo_col_btn, histo_col_preview = st.columns([1, 3])
    histo_error = None
    try:
        base_price_value = _resolve_base_nightly_price()
    except ValueError as exc:
        base_price_value = None
        histo_error = str(exc)

    with histo_col_btn:
        regen_clicked = st.button(
            "(Re)générer graphique",
            key="regen_estimation_histo",
            disabled=base_price_value is None,
        )
        if histo_error:
            st.error(histo_error)
        if regen_clicked and base_price_value is not None:
            try:
                plot_path = build_estimation_histo(base_price_value)
                st.session_state["estimation_histo_png"] = plot_path
                st.success("Graphique mis à jour.")
            except Exception as exc:
                st.error(f"Échec de la génération du graphique: {exc}")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    default_plot_path = os.path.join(base_dir, "out", "plots", "estimation_histo.png")
    preview_path = st.session_state.get("estimation_histo_png", default_plot_path)
    if not preview_path or not os.path.exists(preview_path):
        preview_path = None

    with histo_col_preview:
        if preview_path:
            st.image(preview_path, caption="Évo du prix/nuitée")
        elif not histo_error:
            st.caption("Graphique non généré pour le moment.")

    # Mapping Estimation
    metro = st.session_state.get('metro_lines_auto') or []
    bus = st.session_state.get('bus_lines_auto') or []
    metro_str = ", ".join(f"Ligne {x.get('ref')}" for x in metro if x.get('ref'))
    bus_str = ", ".join(f"Bus {x.get('ref')}" for x in bus if x.get('ref'))
    mapping = {
        # Slide 4
        "[[ADRESSE]]": st.session_state.get("bien_addr",""),
        "[[QUARTIER_TEXTE]]": st.session_state.get("q_txt",""),
        "[[TRANSPORT_TAXI_TEXTE]]": st.session_state.get('q_tx', ''),
        "[[TRANSPORT_METRO_TEXTE]]": metro_str,
        "[[TRANSPORT_BUS_TEXTE]]": bus_str,
        "[[INCONTOURNABLE_1_NOM]]": st.session_state.get('i1', ''),
        "[[INCONTOURNABLE_2_NOM]]": st.session_state.get('i2', ''),
        "[[INCONTOURNABLE_3_NOM]]": st.session_state.get('i3', ''),
        "[[SPOT_1_NOM]]": st.session_state.get('s1', ''),
        "[[SPOT_2_NOM]]": st.session_state.get('s2', ''),
        "[[VISITE_1_NOM]]": st.session_state.get('v1', ''),
        "[[VISITE_2_NOM]]": st.session_state.get('v2', ''),
        # Slide 5 (valeurs numériques + PF/Challenges)
        "[[NB_SURFACE]]": f"{st.session_state.get('bien_surface',0):.0f}",
        "[[NB_PIECES]]": f"{int(st.session_state.get('bien_pieces',0))}",
        "[[NB_SDB]]": f"{int(st.session_state.get('bien_sdb',0))}",
        "[[NB_COUCHAGES]]": f"{int(st.session_state.get('bien_couchages',0))}",
        "[[MODE_CHAUFFAGE]]": st.session_state.get('bien_chauffage',''),
        "[[POINT_FORT_1]]": st.session_state.get('pf1',''),
        "[[POINT_FORT_2]]": st.session_state.get('pf2',''),
        "[[CHALLENGE_1]]": st.session_state.get('ch1',''),
        "[[CHALLENGE_2]]": st.session_state.get('ch2',''),
        # Slide 6
        "[[PRIX_NUIT]]": f"{st.session_state.get('rn_prix',0):.0f} €",
        "[[TAUX_OCC]]": f"{st.session_state.get('rn_occ',0)} %",
        "[[REV_BRUT]]": f"{REV_BRUT:.0f} €",
        "[[FRAIS_GEN]]": f"{FRAIS_GEN:.0f} €",
        "[[REV_NET]]": f"{REV_NET:.0f} €",
        "[[JOURS_OCC]]": f"{JOURS_OCC:.1f} j",
        "[[PRIX_PESSIMISTE]]": f"{PRIX_PESS:.0f} €",
        "[[PRIX_CIBLE]]": f"{PRIX_CIBLE:.0f} €",
        "[[PRIX_OPTIMISTE]]": f"{PRIX_OPT:.0f} €",
    }

    # Images for VISITE_1/2 (from confirmed paths)
    image_by_shape = {}
    p1 = st.session_state.get('visite1_img_path')
    p2 = st.session_state.get('visite2_img_path')
    if p1 and os.path.exists(p1):
        image_by_shape["VISITE_1_MASK"] = p1
    if p2 and os.path.exists(p2):
        image_by_shape["VISITE_2_MASK"] = p2

    # === MAP ===
    lat = st.session_state.get("geo_lat")
    lon = st.session_state.get("geo_lon")
    if lat and lon:
        try:
            map_path = build_static_map(lat, lon, pixel_radius=60, size=(900, 900))
            image_by_shape["MAP_MASK"] = map_path
        except Exception as e:
            st.warning(f"Carte non générée: {e}")

    print("DBG image_by_shape (final):", image_by_shape)

    # ---- Generate Estimation ----
    st.subheader("Générer l'Estimation (PPTX)")
    est_tpl_path = resolve_est_path(chosen_est)
    if st.button("Générer le PPTX (Estimation)"):
        if not est_tpl_path or not os.path.exists(est_tpl_path):
            st.error("Aucun template PPTX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus.")
            st.stop()
        try:
            base_price_value = _resolve_base_nightly_price()
        except ValueError as exc:
            st.error(f"Impossible de générer le graphique: {exc}")
            st.stop()
        try:
            histo_path = build_estimation_histo(base_price_value)
            st.session_state["estimation_histo_png"] = histo_path
        except Exception as exc:
            st.error(f"Graphique estimation indisponible: {exc}")
            st.stop()
        pptx_out = os.path.join(OUT_DIR, f"Estimation - {st.session_state.get('bien_addr','bien')}.pptx")
        generate_estimation_pptx(
            est_tpl_path,
            pptx_out,
            mapping,
            chart_image=histo_path,
            image_by_shape=image_by_shape or None,
        )
        st.success(f"OK: {pptx_out}")
        with open(pptx_out, "rb") as f:
            st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))

    # =====================================================
    # =============== MANDAT PAGE =========================
    # =====================================================
