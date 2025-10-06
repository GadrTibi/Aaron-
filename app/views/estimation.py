import os
import streamlit as st

from app.services.revenue import RevenueInputs, compute_revenue
from app.services.plots import build_estimation_histo
from app.services.pptx_fill import generate_estimation_pptx
from app.services.poi import (
    list_metro_lines,
    list_bus_lines,
)
from app.services.poi_fetcher import POIService
from app.services.geocode import geocode_address
from app.services.image_fetcher import debug_fetch_poi
from app.services.map_image import build_static_map

from .utils import _sanitize_filename, list_templates


_poi_service = POIService()


def _poi_name(item: dict) -> str:
    tags = item.get("tags") or {}
    name = item.get("name")
    if name:
        return str(name)
    for key in ("ref", "tourism", "amenity", "historic", "leisure", "public_transport", "railway"):
        value = tags.get(key)
        if value:
            return str(value)
    return f"POI {item.get('id', '')}".strip()


def _poi_label(item: dict) -> str:
    name = _poi_name(item)
    distance = item.get("distance")
    if distance:
        mins = int(round(float(distance) / 80.0)) if distance else 0
        return f"{name} ({int(distance)} m · {mins} min)"
    return name


def _store_poi_result(category: str, result: dict) -> None:
    st.session_state[f"{category}_poi_result"] = result


def _get_poi_result(category: str) -> dict:
    return st.session_state.get(f"{category}_poi_result", {})


def _render_zero_state(category: str) -> None:
    st.info("Aucun résultat pour ce périmètre. Essayez d’augmenter le rayon.")
    radius_options = [800, 1500, 3000]
    current_radius = int(st.session_state.get("radius_m", 1200))
    if current_radius not in radius_options:
        radius_options.append(current_radius)
    radius_options = sorted(set(radius_options))
    default_index = radius_options.index(current_radius) if current_radius in radius_options else 0
    new_radius = st.selectbox(
        "Rayon suggéré",
        options=radius_options,
        index=default_index,
        key=f"{category}_radius_select",
    )
    if new_radius != current_radius:
        st.session_state["radius_m"] = new_radius


def _format_transport_summary(items: list[dict]) -> dict[str, str]:
    summary = {"taxi": "", "metro": "", "bus": ""}
    for item in items:
        tags = item.get("tags") or {}
        label = _poi_label(item)
        if tags.get("amenity") == "taxi" and not summary["taxi"]:
            summary["taxi"] = label
        elif tags.get("railway") in {"station", "tram_stop", "subway", "halt"} and not summary["metro"]:
            summary["metro"] = label
        elif tags.get("highway") == "bus_stop" and not summary["bus"]:
            summary["bus"] = label
        elif tags.get("public_transport") and not summary["metro"]:
            summary["metro"] = label
    return summary


def _default_indices(items: list[dict], stored: list[str], limit: int) -> list[int]:
    name_to_index: dict[str, int] = {}
    for idx, item in enumerate(items):
        name_to_index.setdefault(_poi_name(item), idx)
    indices: list[int] = []
    for value in stored:
        if value:
            idx = name_to_index.get(value)
            if idx is not None:
                indices.append(idx)
    if not indices:
        indices = list(range(min(len(items), limit)))
    return indices[:limit]


def _fetch_and_store_pois(category: str, lat: float, lon: float, radius: int, lang: str = "fr") -> None:
    with st.spinner("Recherche de points d'intérêt…"):
        items = _poi_service.get_pois(lat, lon, radius_m=radius, category=category, lang=lang)
    last = _poi_service.last_result
    result = {
        "items": items,
        "provider": last.provider if last else "",
        "endpoint": last.endpoint if last else None,
        "status": last.status if last else None,
        "duration_ms": last.duration_ms if last else None,
    }
    _store_poi_result(category, result)


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

def render(config):
    TPL_DIR = config['TPL_DIR']
    EST_TPL_DIR = config['EST_TPL_DIR']
    OUT_DIR = config['OUT_DIR']

    if "visites_locked" not in st.session_state:
        st.session_state['visites_locked'] = False

    # ---------- APPLY PENDING PREFILL BEFORE WIDGETS ----------
    if "__prefill" in st.session_state and isinstance(st.session_state["__prefill"], dict):
        # apply and pop so we don't loop
        for k, v in st.session_state["__prefill"].items():
            st.session_state[k] = v
        st.session_state.pop("__prefill", None)

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
                radius = int(st.session_state.get("radius_m", 1200))
                _fetch_and_store_pois("transport", lat, lon, radius)
                transport_items = _get_poi_result("transport").get("items", [])
                summary = _format_transport_summary(transport_items)
                st.session_state["q_tx"] = summary.get("taxi", "")
                st.session_state['metro_lines_auto'] = list_metro_lines(lat, lon, radius_m=radius)
                st.session_state['bus_lines_auto'] = list_bus_lines(lat, lon, radius_m=radius)
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

    transport_result = _get_poi_result("transport")
    transport_items = transport_result.get("items", [])
    if transport_items:
        st.caption(f"source : {transport_result.get('provider', 'overpass')}")
        for item in transport_items[:5]:
            st.markdown(f"- {_poi_label(item)}")
    elif transport_result:
        st.caption(f"source : {transport_result.get('provider', 'overpass')}")
        _render_zero_state("transport")

    # ---- Incontournables (3), Spots (2), Visites (2 + images) ----
    st.subheader("Adresses du quartier (Slide 4)")
    if st.button("Charger Incontournables (≈15)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                radius = int(st.session_state.get("radius_m", 1200))
                _fetch_and_store_pois("incontournables", lat, lon, radius)
            except Exception as e:
                st.warning(f"Incontournables non chargés: {e}")
    inco_result = _get_poi_result("incontournables")
    inco_items = inco_result.get("items", [])
    if inco_items:
        labels = [_poi_label(item) for item in inco_items]
        stored = [st.session_state.get('i1', ''), st.session_state.get('i2', ''), st.session_state.get('i3', '')]
        defaults = _default_indices(inco_items, stored, 3)
        selection = st.multiselect(
            "Incontournables (max 3)",
            options=list(range(len(inco_items))),
            default=defaults,
            format_func=lambda idx: labels[idx],
        )
        selection = selection[:3]
        names = [_poi_name(inco_items[idx]) for idx in selection]
        st.session_state['i1'] = names[0] if len(names) > 0 else ""
        st.session_state['i2'] = names[1] if len(names) > 1 else ""
        st.session_state['i3'] = names[2] if len(names) > 2 else ""
        st.caption(f"source : {inco_result.get('provider', 'overpass')}")
    elif inco_result:
        st.caption(f"source : {inco_result.get('provider', 'overpass')}")
        _render_zero_state("incontournables")

    if st.button("Charger Spots (≈10)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                radius = int(st.session_state.get("radius_m", 1200))
                _fetch_and_store_pois("spots", lat, lon, radius)
            except Exception as e:
                st.warning(f"Spots non chargés: {e}")
    spots_result = _get_poi_result("spots")
    spots_items = spots_result.get("items", [])
    if spots_items:
        labels = [_poi_label(item) for item in spots_items]
        stored = [st.session_state.get('s1', ''), st.session_state.get('s2', '')]
        defaults = _default_indices(spots_items, stored, 2)
        selection = st.multiselect(
            "Spots (max 2)",
            options=list(range(len(spots_items))),
            default=defaults,
            format_func=lambda idx: labels[idx],
        )
        selection = selection[:2]
        names = [_poi_name(spots_items[idx]) for idx in selection]
        st.session_state['s1'] = names[0] if len(names) > 0 else ""
        st.session_state['s2'] = names[1] if len(names) > 1 else ""
        st.caption(f"source : {spots_result.get('provider', 'overpass')}")
    elif spots_result:
        st.caption(f"source : {spots_result.get('provider', 'overpass')}")
        _render_zero_state("spots")

    st.markdown("**Lieux à visiter (2) — images auto (Unsplash → Pexels → Wikimedia)**")
    if st.button("Charger Visites (≈10)"):
        lat, lon = _geocode_main_address()
        if lat is not None:
            try:
                radius = int(st.session_state.get("radius_m", 1200))
                _fetch_and_store_pois("lieux_a_visiter", lat, lon, radius)
            except Exception as e:
                st.warning(f"Visites non chargées: {e}")
    visites_result = _get_poi_result("lieux_a_visiter")
    visites_items = visites_result.get("items", [])
    if visites_items:
        labels = [_poi_label(item) for item in visites_items]
        stored = [st.session_state.get('v1', ''), st.session_state.get('v2', '')]
        defaults = _default_indices(visites_items, stored, 2)
        sel_vis = st.multiselect(
            "Lieux à visiter (max 2)",
            options=list(range(len(visites_items))),
            default=defaults,
            format_func=lambda idx: labels[idx],
        )
        sel_vis = sel_vis[:2]
        names = [_poi_name(visites_items[idx]) for idx in sel_vis]
    else:
        sel_vis = []
        names = []
        if visites_result:
            st.caption(f"source : {visites_result.get('provider', 'overpass')}")
            _render_zero_state("lieux_a_visiter")
    if visites_items:
        st.caption(f"source : {visites_result.get('provider', 'overpass')}")
    prev_v1, prev_v2 = st.session_state.get('v1', ''), st.session_state.get('v2', '')
    new_v1 = names[0] if len(names) > 0 else ""
    new_v2 = names[1] if len(names) > 1 else ""
    if new_v1 != prev_v1:
        st.session_state.pop('visite1_data', None)
    if new_v2 != prev_v2:
        st.session_state.pop('visite2_data', None)
    st.session_state['v1'] = new_v1
    st.session_state['v2'] = new_v2

    if "visite1_data" not in st.session_state:
        st.session_state['visite1_data'] = None
    if "visite2_data" not in st.session_state:
        st.session_state['visite2_data'] = None

    address = st.session_state.get("bien_addr", "")
    country = st.session_state.get("bien_country") or st.session_state.get("bien_pays")

    visites_locked = st.session_state.get('visites_locked', False)
    if visites_locked:
        p1 = st.session_state.get('visite1_img_path', '')
        p2 = st.session_state.get('visite2_img_path', '')
        prov1 = st.session_state.get('visite1_provider') or "Placeholder"
        prov2 = st.session_state.get('visite2_provider') or "Placeholder"
        st.success(
            "✅ Images confirmées\n"
            f"- Visite 1 : {os.path.basename(p1) if p1 else ''} (source : {prov1})\n"
            f"- Visite 2 : {os.path.basename(p2) if p2 else ''} (source : {prov2})"
        )
        if st.button("Réinitialiser images"):
            st.session_state.pop('visite1_img_path', None)
            st.session_state.pop('visite2_img_path', None)
            st.session_state['visites_locked'] = False
            st.session_state.pop('visite1_data', None)
            st.session_state.pop('visite2_data', None)
            st.session_state.pop('visite1_provider', None)
            st.session_state.pop('visite2_provider', None)
            st.info("Images réinitialisées.")
    else:
        st.info("Cliquez sur « Chercher image » pour chaque visite, puis confirmez.")
        cimg1, cimg2 = st.columns(2)

        def _store_image(slot: str, poi_label: str) -> None:
            if not poi_label:
                st.warning("Sélectionnez d'abord un lieu dans la liste.")
                return
            with st.spinner("Recherche d'image…"):
                final_path, attempts = debug_fetch_poi(poi_label, city=address or None, country=country)
            final_attempt = next((a for a in reversed(attempts) if a.local_path), None)
            provider = final_attempt.provider if final_attempt else ""
            st.session_state[f"{slot}_data"] = {
                "path": final_path,
                "provider": provider,
                "attempts": [
                    {
                        "provider": a.provider,
                        "request_url": a.request_url,
                        "status": a.status,
                        "message": a.message,
                        "image_url": a.image_url,
                        "local_path": a.local_path,
                        "duration_ms": a.duration_ms,
                    }
                    for a in attempts
                ],
            }

        with cimg1:
            if st.button("Chercher image pour Visite 1", key="fetch_visite1"):
                _store_image("visite1", st.session_state.get("v1", ""))
            data1 = st.session_state.get('visite1_data') or {}
            path1 = data1.get("path")
            if path1:
                st.image(path1, width=280)
                provider = data1.get("provider")
                if provider and provider != "placeholder":
                    st.caption(f"Source : {provider}")
                else:
                    st.caption("Source : Placeholder")
            attempts1 = data1.get("attempts") or []
            if attempts1:
                provider_msgs = [
                    f"{item['provider']} ({item['status']})"
                    for item in attempts1
                ]
                st.caption(" • ".join(provider_msgs))
        with cimg2:
            if st.button("Chercher image pour Visite 2", key="fetch_visite2"):
                _store_image("visite2", st.session_state.get("v2", ""))
            data2 = st.session_state.get('visite2_data') or {}
            path2 = data2.get("path")
            if path2:
                st.image(path2, width=280)
                provider = data2.get("provider")
                if provider and provider != "placeholder":
                    st.caption(f"Source : {provider}")
                else:
                    st.caption("Source : Placeholder")
            attempts2 = data2.get("attempts") or []
            if attempts2:
                provider_msgs = [
                    f"{item['provider']} ({item['status']})"
                    for item in attempts2
                ]
                st.caption(" • ".join(provider_msgs))
        if st.button("Confirmer les images"):
            data1 = st.session_state.get('visite1_data') or {}
            data2 = st.session_state.get('visite2_data') or {}
            path1 = data1.get("path")
            path2 = data2.get("path")
            if not (path1 and path2):
                st.warning("Sélection incomplète…")
            else:
                st.session_state['visite1_img_path'] = path1
                st.session_state['visite2_img_path'] = path2
                prov1 = data1.get("provider")
                prov2 = data2.get("provider")
                st.session_state['visite1_provider'] = "Placeholder" if not prov1 or prov1 == "placeholder" else prov1
                st.session_state['visite2_provider'] = "Placeholder" if not prov2 or prov2 == "placeholder" else prov2
                st.session_state['visites_locked'] = True
                st.success("Images confirmées (2/2). Elles seront utilisées à la génération.")
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
    if p1:
        image_by_shape["VISITE_1_MASK"] = p1
    if p2:
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
