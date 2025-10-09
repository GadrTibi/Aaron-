import os
from typing import Iterable

import streamlit as st

from app.services.revenue import RevenueInputs, compute_revenue
from app.services.plots import build_estimation_histo
from app.services.pptx_fill import generate_estimation_pptx
from app.services.poi import (
    fetch_transports,
    list_metro_lines,
    list_bus_lines,
)
from app.services.geocode import geocode_address
from app.services.map_image import build_static_map
from services.places_google import GPlace, GooglePlacesService
from services.wiki_images import ImageCandidate, WikiImageService

from .settings_keys import read_local_secret
from .utils import _sanitize_filename, list_templates


@st.cache_data(ttl=120)
def _load_google_places(
    category: str,
    api_key: str,
    lat: float,
    lon: float,
    radius_m: int,
    limit: int,
) -> list[GPlace]:
    service = GooglePlacesService(api_key)
    if category == "incontournables":
        return service.list_incontournables(lat, lon, radius_m, limit)
    if category == "spots":
        return service.list_spots(lat, lon, radius_m, limit)
    if category == "visits":
        return service.list_visits(lat, lon, radius_m, limit)
    raise ValueError(f"Catégorie Google Places inconnue: {category}")


def _restore_candidates(key: str) -> list[ImageCandidate]:
    stored = st.session_state.get(key, [])
    candidates: list[ImageCandidate] = []
    for item in stored:
        if isinstance(item, ImageCandidate):
            candidates.append(item)
        elif isinstance(item, dict):
            candidates.append(ImageCandidate.from_dict(item))
    return candidates


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


def _format_line_labels(items: list, prefix: str) -> str:
    labels: list[str] = []
    for item in items:
        if isinstance(item, str):
            labels.append(item)
            continue
        if isinstance(item, dict):
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
                taxi_items, taxi_debug = fetch_transports(lat, lon, radius_m=radius)
                metro_items, metro_debug = list_metro_lines(
                    lat, lon, radius_m=radius, include_debug=True
                )
                bus_items, bus_debug = list_bus_lines(lat, lon, radius_m=radius)
                st.session_state["q_tx"] = _format_taxi_summary(taxi_items)
                st.session_state['metro_lines_auto'] = metro_items
                st.session_state['bus_lines_auto'] = bus_items
                _display_transport_caption(taxi_debug, metro_debug, bus_debug)
            except Exception as e:
                st.warning(f"Transports non chargés: {e}")
        else:
            st.session_state["q_tx"] = ""
            st.session_state['metro_lines_auto'] = []
            st.session_state['bus_lines_auto'] = []
    taxi_txt = st.session_state.get("q_tx", "")
    metro_auto = st.session_state.get('metro_lines_auto', [])
    bus_auto = st.session_state.get('bus_lines_auto', [])
    metro_refs = _format_line_labels(metro_auto, "Ligne")
    bus_refs = _format_line_labels(bus_auto, "Bus")
    st.write(f"Taxi : {taxi_txt or '—'}")
    st.write(f"Métro : {metro_refs or '—'}")
    st.write(f"Bus : {bus_refs or '—'}")

    # ---- Incontournables (3), Spots (2), Visites (2 + images) ----
    st.subheader("Adresses du quartier (Slide 4)")
    api_key = read_local_secret("GOOGLE_MAPS_API_KEY")
    radius_raw = st.session_state.get("radius_m", 1200)
    try:
        radius_m = int(radius_raw)
    except (TypeError, ValueError):
        radius_m = 1200
    lat_raw = st.session_state.get("geo_lat")
    lon_raw = st.session_state.get("geo_lon")

    def _to_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    lat_val = _to_float(lat_raw)
    lon_val = _to_float(lon_raw)

    incontournables_items: list[GPlace] = []
    spots_items: list[GPlace] = []
    visits_items: list[GPlace] = []

    if not api_key:
        st.warning("Clé Google manquante.")
    elif lat_val is None or lon_val is None:
        st.info("Adresse non géocodée. Lancez la recherche d'adresse avant de charger les lieux.")
    else:
        try:
            incontournables_items = _load_google_places(
                "incontournables", api_key, lat_val, lon_val, radius_m, 15
            )
        except Exception as exc:
            st.warning(f"Incontournables non chargés: {exc}")
        try:
            spots_items = _load_google_places("spots", api_key, lat_val, lon_val, radius_m, 10)
        except Exception as exc:
            st.warning(f"Spots non chargés: {exc}")
        try:
            visits_items = _load_google_places("visits", api_key, lat_val, lon_val, radius_m, 10)
        except Exception as exc:
            st.warning(f"Visites non chargées: {exc}")

    st.caption("source: Google Places")

    def _select_places(label: str, items: list[GPlace], keys: Iterable[str]) -> list[str]:
        key_list = list(keys)
        max_selection = len(key_list)
        if not items:
            st.multiselect(label, options=[], default=[])
            for key in key_list:
                st.session_state[key] = ""
            return []

        options = list(range(len(items)))
        stored_names = [
            st.session_state.get(key, "")
            for key in key_list
            if st.session_state.get(key)
        ]
        default_indices: list[int] = []
        for name in stored_names:
            for idx, place in enumerate(items):
                if place.name == name and idx not in default_indices:
                    default_indices.append(idx)
                    break
        if not default_indices:
            default_indices = options[:max_selection]

        selection = st.multiselect(
            label,
            options=options,
            default=default_indices[:max_selection],
            format_func=lambda idx: f"{items[idx].name} ({round(items[idx].distance_m)} m)",
        )
        selection = selection[:max_selection]
        chosen_names = [items[idx].name for idx in selection]
        for offset, key in enumerate(key_list):
            st.session_state[key] = chosen_names[offset] if offset < len(chosen_names) else ""
        return chosen_names

    _select_places("Incontournables (max 3)", incontournables_items, ("i1", "i2", "i3"))
    _select_places("Spots (max 2)", spots_items, ("s1", "s2"))

    prev_v1 = st.session_state.get("v1", "")
    prev_v2 = st.session_state.get("v2", "")
    _select_places("Lieux à visiter (max 2)", visits_items, ("v1", "v2"))
    new_v1 = st.session_state.get("v1", "")
    new_v2 = st.session_state.get("v2", "")
    if new_v1 != prev_v1:
        for key in ("visite1_candidates", "visite1_choice", "visite1_img_path", "visite1_provider"):
            st.session_state.pop(key, None)
    if new_v2 != prev_v2:
        for key in ("visite2_candidates", "visite2_choice", "visite2_img_path", "visite2_provider"):
            st.session_state.pop(key, None)

    st.session_state["visits_lookup"] = {place.name: place for place in visits_items}

    st.caption("images: Wikimedia")
    col_v1, col_v2 = st.columns(2)

    def _render_visit_column(slot: str, title_key: str, column) -> None:
        title_value = st.session_state.get(title_key, "")
        with column:
            st.markdown(f"**{('Visite 1' if slot == 'visite1' else 'Visite 2')}**")
            if st.button(f"Trouver images {('Visite 1' if slot == 'visite1' else 'Visite 2')}", key=f"find_{slot}"):
                if not title_value:
                    st.warning("Sélectionnez d'abord un lieu dans la liste.")
                else:
                    try:
                        service = WikiImageService()
                        candidates = service.candidates(title=title_value, city=None, country=None, limit=5)
                    except Exception as exc:
                        st.warning(f"Images indisponibles: {exc}")
                    else:
                        st.session_state[f"{slot}_candidates"] = [cand.to_dict() for cand in candidates]
                        st.session_state.pop(f"{slot}_choice", None)

            candidates = _restore_candidates(f"{slot}_candidates")
            if candidates:
                options = list(range(len(candidates)))
                choice_key = f"{slot}_choice"
                if options and st.session_state.get(choice_key) not in options:
                    st.session_state[choice_key] = options[0]
                selected_idx = st.radio(
                    "Sélectionner une image",
                    options=options,
                    format_func=lambda idx: f"Option {idx + 1} – source: {candidates[idx].source}",
                    key=choice_key,
                )
                cols = st.columns(min(len(candidates), 5))
                for idx, candidate in enumerate(candidates):
                    with cols[idx % len(cols)]:
                        st.image(candidate.thumb_url or candidate.url, width=160, caption=f"Option {idx + 1}")
                if st.button("Valider l'image", key=f"confirm_{slot}"):
                    chosen = candidates[selected_idx]
                    try:
                        path = WikiImageService().download(chosen.url)
                    except Exception as exc:
                        st.warning(f"Téléchargement impossible: {exc}")
                    else:
                        st.session_state[f"{slot}_img_path"] = path
                        st.session_state[f"{slot}_provider"] = chosen.source or "Wikimedia"
                        st.success("Image enregistrée.")

            img_path = st.session_state.get(f"{slot}_img_path")
            if img_path:
                st.image(img_path, width=260)
                provider = st.session_state.get(f"{slot}_provider") or "Wikimedia"
                st.caption(f"Source : {provider}")
                if st.button("Réinitialiser l'image", key=f"reset_{slot}"):
                    for key in (f"{slot}_img_path", f"{slot}_provider"):
                        st.session_state.pop(key, None)

    _render_visit_column("visite1", "v1", col_v1)
    _render_visit_column("visite2", "v2", col_v2)

    st.slider(
        "Rayon (m)",
        min_value=300,
        max_value=3000,
        value=st.session_state.get("radius_m", 1200),
        step=100,
        key="radius_m",
    )

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
    metro_str = _format_line_labels(list(metro), "Ligne")
    bus_str = _format_line_labels(list(bus), "Bus")
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
