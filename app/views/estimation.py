import os
from time import perf_counter
from typing import Iterable, Optional

import streamlit as st
from streamlit.errors import StreamlitAPIException

from app.services.generation_report import GenerationReport
from app.services.geo_helpers import ensure_geocoded
from app.services.geocode_cache import normalize_address
from app.services.map_image import build_static_map
from app.services.plots import build_estimation_histo
from app.services.poi_facade import POIResult, get_pois
from app.services.provider_status import get_provider_status
from app.services.quartier_enricher import enrich_quartier_and_transports
from app.services.pptx_fill import generate_estimation_pptx
from app.services.pptx_requirements import (
    get_estimation_detectors,
    get_estimation_requirements,
)
from app.services.transports_facade import get_transports
from app.services.revenue import RevenueInputs, compute_revenue
from app.services.template_validation import validate_pptx_template
from services.image_uploads import save_uploaded_image
from services.wiki_images import ImageCandidate, WikiImageService

from .utils import (
    _sanitize_filename,
    apply_pending_fields,
    list_templates,
    render_generation_report,
    render_template_validation,
)


DEFAULT_RADIUS_M = 300


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

def _collect_line_refs(items: list, limit: Optional[int] = None) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, dict):
            value = item.get("ref") or item.get("name")
        elif isinstance(item, str):
            value = item
        else:
            value = str(item) if item is not None else ""
        ref = str(value).strip()
        if not ref:
            continue
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if limit is not None and len(refs) >= limit:
            break
    return refs


def _format_line_labels(items: list, prefix: str) -> str:
    refs = _collect_line_refs(items)
    labels: list[str] = []
    for ref in refs:
        if prefix and not ref.lower().startswith(prefix.lower()):
            labels.append(f"{prefix} {ref}")
        else:
            labels.append(ref)
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


def _compact_provider_status() -> str:
    status = get_provider_status()
    labels = []
    order = [
        ("Google Places", "Google"),
        ("Geoapify", "Geoapify"),
        ("OpenTripMap", "OTM"),
        ("Wikimedia", "Wiki"),
    ]
    for key, short in order:
        entry = status.get(key, {})
        emoji = "✅" if entry.get("enabled") else "❌"
        labels.append(f"{short} {emoji}")
    return " / ".join(labels)


def render(config):
    TPL_DIR = config['TPL_DIR']
    EST_TPL_DIR = config['EST_TPL_DIR']
    OUT_DIR = config['OUT_DIR']
    run_report = GenerationReport()

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

    geocode_debug = st.checkbox("Debug géocodage", key="geocode_debug_toggle")

    def _geocode_main_address(show_debug: bool = False):
        addr_raw = st.session_state.get("bien_addr", "") or ""
        addr = addr_raw.strip()
        normalized_addr = normalize_address(addr)
        st.session_state["geocode_address_norm"] = normalized_addr
        perf_geocode: dict[str, object] = {}

        if not addr:
            st.error("Adresse manquante pour le géocodage.")
            st.session_state["geo_lat"] = None
            st.session_state["geo_lon"] = None
            st.session_state["geocode_provider"] = ""
            return None, None, "", perf_geocode

        cache_hit = (
            st.session_state.get("geo_lat") is not None
            and st.session_state.get("geo_lon") is not None
            and st.session_state.get("geocoded_address") == normalized_addr
        )

        last_warning_before = len(run_report.provider_warnings)
        start = perf_counter()
        try:
            if cache_hit:
                lat, lon, provider_used = ensure_geocoded(addr, report=run_report)
            else:
                with st.spinner("Géocodage…"):
                    lat, lon, provider_used = ensure_geocoded(addr, report=run_report)
        except ValueError as exc:
            st.error(str(exc))
            st.session_state["geo_lat"] = None
            st.session_state["geo_lon"] = None
            st.session_state["geocode_provider"] = ""
            return None, None, "", perf_geocode
        except Exception as exc:
            st.error(f"Géocodage impossible: {exc}")
            st.session_state["geo_lat"] = None
            st.session_state["geo_lon"] = None
            st.session_state["geocode_provider"] = ""
            return None, None, "", perf_geocode
        duration = perf_counter() - start

        last_warning = run_report.provider_warnings[-1] if run_report.provider_warnings else None
        provider_label = st.session_state.get("geocode_provider") or provider_used or "Nominatim"
        if lat is None or lon is None:
            if last_warning and len(run_report.provider_warnings) > last_warning_before:
                st.error(f"Géocodage échoué: {last_warning}")
            else:
                st.error("Géocodage échoué: adresse introuvable.")
        else:
            st.success(f"Adresse géocodée via {provider_label}: {lat}, {lon}")
            if provider_used == "session_cache":
                st.info("Utilisation des coordonnées en cache session.")
            elif provider_used and provider_used != "Nominatim":
                st.warning(f"Fallback géocodage: {provider_used} utilisé.")
        perf_geocode = {
            "duration": duration,
            "provider": provider_label,
            "cache": "session" if provider_used == "session_cache" else ("network" if lat is not None else "error"),
        }
        run_report.add_note(f"Géocodage: {duration:.2f}s via {provider_label} ({perf_geocode['cache']}).")

        if show_debug:
            st.info("Debug géocodage activé :")
            st.write(f"Adresse envoyée: {addr}")
            st.write(f"Provider utilisé/principal: {provider_label}")
            st.write(f"Durée: {duration:.2f}s")
            st.write(f"Cache: {perf_geocode['cache']}")
            if run_report.provider_warnings:
                st.warning(" / ".join(run_report.provider_warnings[-3:]))
        return lat, lon, provider_label, perf_geocode

    def _auto_geocode_or_stop(action_label: str, *, stop_on_error: bool = True) -> tuple[float | None, float | None, str]:
        addr_raw = (st.session_state.get("bien_addr", "") or "").strip()
        normalized_addr = normalize_address(addr_raw)
        needs_spinner = (
            st.session_state.get("geo_lat") is None
            or st.session_state.get("geo_lon") is None
            or st.session_state.get("geocoded_address") != normalized_addr
        )
        try:
            if needs_spinner:
                with st.spinner("Géocodage automatique…"):
                    return ensure_geocoded(addr_raw, report=run_report)
            return ensure_geocoded(addr_raw, report=run_report)
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"{action_label} impossible: {exc}")
        if stop_on_error:
            st.stop()
        return None, None, ""

    # ---- Quartier & transports (Slide 4) ----
    st.subheader("Quartier & Transports (Slide 4)")
    radius_default_raw = st.session_state.get("radius_m", DEFAULT_RADIUS_M)
    try:
        radius_default = int(radius_default_raw)
    except (TypeError, ValueError):
        radius_default = DEFAULT_RADIUS_M
        st.session_state["radius_m"] = DEFAULT_RADIUS_M
    st.slider(
        "Rayon (m)",
        min_value=300,
        max_value=3000,
        value=radius_default,
        step=100,
        key="radius_m",
        help="Distance utilisée pour les lieux et transports.",
    )
    for key in ("quartier_intro", "transports_metro_texte", "transports_bus_texte", "transports_taxi_texte"):
        st.session_state.setdefault(key, "")

    apply_pending_fields(
        st.session_state,
        "_quartier_pending",
        ("quartier_intro", "transports_metro_texte", "transports_bus_texte", "transports_taxi_texte"),
    )

    col_btn, col_hint = st.columns([1, 2])
    with col_btn:
        enrich_clicked = st.button("✨ Enrichir auto", disabled=not st.session_state.get("bien_addr", "").strip())
    with col_hint:
        st.caption("Saisissez l'adresse puis lancez l'enrichissement. Vous pouvez modifier manuellement si besoin.")

    if enrich_clicked:
        perf_transports: dict[str, object] = {}
        perf_geocode: dict[str, object] = {}
        addr_raw = st.session_state.get("bien_addr", "").strip()
        with st.spinner("Enrichissement quartier & transports…"):
            try:
                _auto_geocode_or_stop("Géocodage automatique (enrichissement)", stop_on_error=False)
            except Exception:
                pass
            try:
                payload = enrich_quartier_and_transports(addr_raw, report=run_report)
                st.session_state["_quartier_pending"] = {
                    "quartier_intro": payload.get("quartier_intro", st.session_state.get("quartier_intro", "")),
                    "transports_metro_texte": payload.get("transports_metro_texte", st.session_state.get("transports_metro_texte", "")),
                    "transports_bus_texte": payload.get("transports_bus_texte", st.session_state.get("transports_bus_texte", "")),
                    "transports_taxi_texte": payload.get("transports_taxi_texte", st.session_state.get("transports_taxi_texte", "")),
                }
                st.rerun()
            except Exception as exc:
                message = str(exc)
                if isinstance(exc, StreamlitAPIException) or "cannot be modified after the widget" in message:
                    st.error("Erreur UI Streamlit: mise à jour des champs après instanciation. Correctif appliqué.")
                else:
                    st.error(f"LLM indisponible: {exc}")

    quartier_intro = st.text_area(
        "Intro quartier (2-3 phrases)",
        key="quartier_intro",
    )
    st.session_state["q_txt"] = quartier_intro
    col_q1, col_q2 = st.columns([1, 1])
    with col_q1:
        metro_txt = st.text_area(
            "Transports métro (3-4 lignes)",
            key="transports_metro_texte",
        )
        bus_txt = st.text_area(
            "Transports bus (3-4 lignes)",
            key="transports_bus_texte",
        )
    with col_q2:
        taxi_txt = st.text_area(
            "Transports taxi (1-2 lignes)",
            key="transports_taxi_texte",
        )
        st.session_state["q_tx"] = taxi_txt

    with st.expander("Ancienne méthode (debug)", expanded=False):
        perf_transports: dict[str, object] = {}
        transport_mode = st.selectbox(
            "Mode transports",
            options=["FAST", "ENRICHED", "FULL"],
            index=0,
            help="FAST (Overpass uniquement, recommandé), ENRICHED (Overpass + Google si disponible), FULL (ajoute GTFS).",
            key="legacy_transport_mode",
        )
        if st.button("Remplir Transports (auto)", key="legacy_transports_btn"):
            lat, lon, provider_used, perf_geocode = _geocode_main_address(show_debug=geocode_debug)
            if lat is not None:
                start_tr = perf_counter()
                with st.spinner("Chargement des transports…"):
                    try:
                        radius_raw = st.session_state.get("radius_m", DEFAULT_RADIUS_M)
                        try:
                            radius = int(radius_raw)
                        except (TypeError, ValueError):
                            radius = DEFAULT_RADIUS_M
                        warning_count = len(run_report.provider_warnings)
                        tr = get_transports(lat, lon, radius_m=radius, mode=transport_mode, report=run_report)
                        st.session_state["q_tx"] = ", ".join(tr.get("taxis", []))
                        st.session_state["metro_lines_auto"] = tr.get("metro_lines", [])
                        st.session_state["bus_lines_auto"] = tr.get("bus_lines", [])
                        st.session_state["transport_providers"] = tr.get("provider_used", {})
                        new_warnings = run_report.provider_warnings[warning_count:]
                        for warning in new_warnings:
                            st.warning(warning)
                        perf_transports = {
                            "duration": perf_counter() - start_tr,
                            "provider": tr.get("provider_used", {}),
                            "cache": tr.get("cache_status", "miss"),
                            "mode": transport_mode,
                            "metro_count": len(tr.get("metro_lines", [])),
                            "bus_count": len(tr.get("bus_lines", [])),
                            "raw_metro": tr.get("raw_counts", {}).get("metro"),
                            "raw_bus": tr.get("raw_counts", {}).get("bus"),
                        }
                        run_report.add_note(
                            f"Transports: {perf_transports['duration']:.2f}s (cache {perf_transports['cache']}, mode {transport_mode})."
                        )
                    except Exception as e:
                        st.warning(f"Transports non chargés: {e}")
                        st.session_state['transport_providers'] = {}
            else:
                st.session_state["q_tx"] = ""
                st.session_state['metro_lines_auto'] = []
                st.session_state['bus_lines_auto'] = []
                st.session_state['transport_providers'] = {}
            if geocode_debug:
                with st.expander("Détails performance", expanded=True):
                    if perf_geocode:
                        st.write(f"Géocodage: {perf_geocode.get('duration', 0):.2f}s via {perf_geocode.get('provider', '')} ({perf_geocode.get('cache', '')})")
                    if perf_transports:
                        st.write(
                            f"Transports: {perf_transports.get('duration', 0):.2f}s cache={perf_transports.get('cache', '')} "
                            f"bruts métro/bus: {perf_transports.get('raw_metro', '-')}/{perf_transports.get('raw_bus', '-')} "
                            f"affichés métro/bus: {perf_transports.get('metro_count', 0)}/{perf_transports.get('bus_count', 0)}"
                        )

    # ---- Incontournables (3), Spots (2), Visites (2 + images) ----
    st.subheader("Adresses du quartier (Slide 4)")
    st.caption(f"POI providers : {_compact_provider_status()}")
    radius_raw = st.session_state.get("radius_m", DEFAULT_RADIUS_M)
    try:
        radius_m = int(radius_raw)
    except (TypeError, ValueError):
        radius_m = DEFAULT_RADIUS_M

    address_raw = (st.session_state.get("bien_addr", "") or "").strip()
    normalized_address = normalize_address(address_raw)
    if st.session_state.get("_poi_address") and st.session_state.get("_poi_address") != normalized_address:
        for key in ("_poi_results", "_poi_provider", "_poi_radius"):
            st.session_state.pop(key, None)
    if st.session_state.get("_auto_geo_attempted_addr") and st.session_state.get("_auto_geo_attempted_addr") != normalized_address:
        st.session_state.pop("_auto_geo_attempted_addr")

    def _to_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    lat_val = _to_float(st.session_state.get("geo_lat"))
    lon_val = _to_float(st.session_state.get("geo_lon"))

    if (lat_val is None or lon_val is None) and normalized_address and st.session_state.get("_auto_geo_attempted_addr") != normalized_address:
        st.info("Coordonnées manquantes : géocodage automatique en cours…")
        lat_val, lon_val, _ = _auto_geocode_or_stop("Géocodage automatique", stop_on_error=False)
        st.session_state["_auto_geo_attempted_addr"] = normalized_address
        lat_val = _to_float(st.session_state.get("geo_lat"))
        lon_val = _to_float(st.session_state.get("geo_lon"))

    provider_in_state = st.session_state.get("geocode_provider") or ""
    coord_caption = "Non géocodé"
    if lat_val is not None and lon_val is not None:
        provider_label = provider_in_state or "N/A"
        coord_caption = f"Coordonnées: OK ({lat_val:.4f}, {lon_val:.4f}) via {provider_label}"
        if st.session_state.get("geocoded_address") and st.session_state.get("geocoded_address") != normalized_address:
            coord_caption = f"Coordonnées présentes (adresse précédente: {st.session_state.get('geocoded_address')})."

    incontournables_items: list[POIResult] = []
    spots_items: list[POIResult] = []
    visits_items: list[POIResult] = []
    poi_provider = st.session_state.get("_poi_provider", "") if st.session_state.get("_poi_address") == normalized_address else ""

    poi_btn_col, poi_status_col = st.columns([1, 2])
    with poi_btn_col:
        load_poi_clicked = st.button("Charger les lieux automatiquement")
    with poi_status_col:
        st.caption(coord_caption)
        if st.button("🔎 Géocoder maintenant", key="force_geocode_now"):
            manual_lat, manual_lon, manual_provider = _auto_geocode_or_stop("Géocodage automatique", stop_on_error=False)
            if manual_lat is not None and manual_lon is not None:
                lat_val, lon_val = manual_lat, manual_lon
                st.success(f"Coordonnées mises à jour (via {manual_provider or provider_in_state or 'géo'}).")

    def _resolve_poi_provider(results: dict[str, list[POIResult]]) -> str:
        for bucket in ("incontournables", "spots", "visits"):
            items = results.get(bucket) or []
            if items:
                return items[0].provider
        return ""

    cached_poi = st.session_state.get("_poi_results") if st.session_state.get("_poi_address") == normalized_address else None
    cached_radius = st.session_state.get("_poi_radius")
    poi_results = cached_poi if cached_poi and cached_radius == radius_m else None
    poi_attempted = load_poi_clicked or poi_results is not None

    if load_poi_clicked:
        lat_val, lon_val, provider_used = _auto_geocode_or_stop("Chargement des lieux")
        if lat_val is None or lon_val is None:
            st.error("Coordonnées introuvables : géocodage automatique requis.")
            st.stop()
        try:
            with st.spinner("Chargement des lieux…"):
                poi_results = get_pois(
                    lat_val,
                    lon_val,
                    radius_m,
                    categories=("incontournables", "spots", "visits"),
                    report=run_report,
                )
        except Exception as exc:
            run_report.add_provider_warning(f"POI indisponibles: {exc}", blocking=True)
            st.error(f"Impossible de charger les lieux automatiquement: {exc}")
        else:
            st.session_state["_poi_results"] = poi_results
            st.session_state["_poi_provider"] = _resolve_poi_provider(poi_results)
            st.session_state["_poi_address"] = normalized_address
            st.session_state["_poi_radius"] = radius_m
            poi_provider = st.session_state.get("_poi_provider", "")

    if poi_results:
        incontournables_items = poi_results.get("incontournables", [])
        spots_items = poi_results.get("spots", [])
        visits_items = poi_results.get("visits", [])
        if not poi_provider:
            poi_provider = _resolve_poi_provider(poi_results)

    if run_report.provider_warnings:
        st.warning(" / ".join(run_report.provider_warnings[-2:]))
    st.caption(f"source: {poi_provider or 'Auto (fallback)'}")
    if poi_attempted and lat_val is not None and lon_val is not None and not (incontournables_items or spots_items or visits_items):
        st.error("Aucun fournisseur POI disponible : saisissez manuellement les lieux clés.")

    def _select_places(label: str, items: list[POIResult], keys: Iterable[str]) -> list[str]:
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
            format_func=lambda idx: f"{items[idx].name} ({round(items[idx].distance_m or 0)} m)",
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
        for key in (
            "visite1_candidates",
            "visite1_choice",
            "visite1_img_path",
            "visite1_provider",
            "visite1_uploaded_path",
        ):
            st.session_state.pop(key, None)
    if new_v2 != prev_v2:
        for key in (
            "visite2_candidates",
            "visite2_choice",
            "visite2_img_path",
            "visite2_provider",
            "visite2_uploaded_path",
        ):
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
                        run_report.add_provider_warning(f"Wikimedia images indisponibles: {exc}")
                        st.warning(f"Images indisponibles: {exc}")
                    else:
                        st.session_state[f"{slot}_candidates"] = [cand.to_dict() for cand in candidates]
                        st.session_state.pop(f"{slot}_choice", None)

            upload_state_key = f"{slot}_uploaded_path"
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
                        run_report.add_provider_warning(f"Téléchargement image Wikimedia impossible: {exc}")
                        st.warning(f"Téléchargement impossible: {exc}")
                    else:
                        st.session_state[f"{slot}_img_path"] = path
                        st.session_state[f"{slot}_provider"] = chosen.source or "Wikimedia"
                        st.success("Image enregistrée.")

            st.markdown("**Ou importer votre propre photo :**")
            uploaded_file = st.file_uploader(
                "Image pour Visite 1" if slot == "visite1" else "Image pour Visite 2",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"{slot}_upload",
            )

            if uploaded_file is not None:
                try:
                    saved_path = save_uploaded_image(uploaded_file, prefix=slot)
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception as exc:  # pragma: no cover - safety net for runtime errors
                    st.warning(f"Échec de l'enregistrement: {exc}")
                else:
                    st.session_state[upload_state_key] = saved_path
                    st.session_state[f"{slot}_provider"] = "image importée"
                    uploaded_path = saved_path
                    st.caption("Image importée enregistrée.")

            uploaded_path = st.session_state.get(upload_state_key)
            img_path = st.session_state.get(f"{slot}_img_path")
            final_preview = uploaded_path or img_path
            if final_preview:
                st.image(final_preview, width=260)
                provider = "image importée" if uploaded_path else (st.session_state.get(f"{slot}_provider") or "Wikimedia")
                st.caption(f"Source : {provider}")
                if st.button("Réinitialiser l'image", key=f"reset_{slot}"):
                    for key in (f"{slot}_img_path", f"{slot}_provider", upload_state_key):
                        st.session_state.pop(key, None)

    _render_visit_column("visite1", "v1", col_v1)
    _render_visit_column("visite2", "v2", col_v2)

    # Points forts & Challenges (Slide 5)
    st.subheader("Points forts & Challenges (Slide 5)")
    colPF, colCH = st.columns(2)
    with colPF:
        point_fort_1 = st.text_input("Point fort 1", st.session_state.get("pf1", "Proche des transports"), key="pf1")
        point_fort_2 = st.text_input("Point fort 2", st.session_state.get("pf2", "Récemment rénové"), key="pf2")
        point_fort_3 = st.text_input("Point fort 3", value=st.session_state.get("pf3", ""), key="pf3")
    with colCH:
        challenge_1 = st.text_input("Challenge 1", st.session_state.get("ch1", "Pas d’ascenseur"), key="ch1")
        challenge_2 = st.text_input("Challenge 2", st.session_state.get("ch2", "Bruit de la rue en journée"), key="ch2")
        challenge_3 = st.text_input("Challenge 3", value=st.session_state.get("ch3", ""), key="ch3")

    st.caption(
        f"Points forts: {', '.join([v for v in [st.session_state.get('pf1'), st.session_state.get('pf2'), st.session_state.get('pf3')] if v])}"
    )
    st.caption(
        f"Challenges: {', '.join([v for v in [st.session_state.get('ch1'), st.session_state.get('ch2'), st.session_state.get('ch3')] if v])}"
    )

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
    metro_refs_tokens = _collect_line_refs(metro, limit=3)
    bus_refs_tokens = _collect_line_refs(bus, limit=3)
    metro_str = ", ".join(metro_refs_tokens)
    bus_str = ", ".join(bus_refs_tokens)
    mapping = {
        # Slide 4
        "[[ADRESSE]]": st.session_state.get("bien_addr",""),
        "[[QUARTIER_TEXTE]]": st.session_state.get("q_txt",""),
        "[[TRANSPORT_TAXI_TEXTE]]": st.session_state.get('q_tx', ''),
        "[[TRANSPORT_METRO_TEXTE]]": metro_str,
        "[[TRANSPORT_BUS_TEXTE]]": bus_str,
        "[[QUARTIER_INTRO]]": st.session_state.get("quartier_intro", ""),
        "[[TRANSPORTS_METRO_TEXTE]]": st.session_state.get("transports_metro_texte", ""),
        "[[TRANSPORTS_BUS_TEXTE]]": st.session_state.get("transports_bus_texte", ""),
        "[[TRANSPORTS_TAXI_TEXTE]]": st.session_state.get("transports_taxi_texte", ""),
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
        "[[POINT_FORT_3]]": st.session_state.get('pf3',''),
        "[[CHALLENGE_1]]": st.session_state.get('ch1',''),
        "[[CHALLENGE_2]]": st.session_state.get('ch2',''),
        "[[CHALLENGE_3]]": st.session_state.get('ch3',''),
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

    # Images for VISITE_1/2 (from confirmed paths or uploaded files)
    image_by_shape = {}
    v1_uploaded = st.session_state.get("visite1_uploaded_path")
    v2_uploaded = st.session_state.get("visite2_uploaded_path")
    p1 = st.session_state.get('visite1_img_path')
    p2 = st.session_state.get('visite2_img_path')

    v1_final = v1_uploaded or p1
    v2_final = v2_uploaded or p2

    if v1_final:
        image_by_shape["VISITE_1_MASK"] = v1_final
    if v2_final:
        image_by_shape["VISITE_2_MASK"] = v2_final

    def _attach_map(target: dict[str, str]) -> None:
        lat = st.session_state.get("geo_lat")
        lon = st.session_state.get("geo_lon")
        if lat and lon:
            try:
                map_path = build_static_map(lat, lon, pixel_radius=60, size=(900, 900))
                target["MAP_MASK"] = map_path
            except Exception as e:
                st.warning(f"Carte non générée: {e}")

    # === MAP ===
    _attach_map(image_by_shape)

    print("DBG image_by_shape (final):", image_by_shape)

    strict_mode = bool(os.environ.get("MFY_STRICT_GENERATION"))
    est_tpl_path = resolve_est_path(chosen_est)
    validation_result = None
    if est_tpl_path and os.path.exists(est_tpl_path):
        try:
            validation_result = validate_pptx_template(
                est_tpl_path,
                set(mapping.keys()),
                get_estimation_requirements(),
                requirement_detectors=get_estimation_detectors(),
            )
        except Exception as exc:
            st.warning(f"Validation du template Estimation impossible: {exc}")
    render_template_validation(validation_result, strict=strict_mode)

    # ---- Generate Estimation ----
    st.subheader("Générer l'Estimation (PPTX)")
    disable_generate = strict_mode and validation_result is not None and validation_result.severity == "KO"
    if st.button("Générer le PPTX (Estimation)", disabled=disable_generate):
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
        _auto_geocode_or_stop("Géocodage automatique (génération)")
        _attach_map(image_by_shape)
        pptx_out = os.path.join(OUT_DIR, f"Estimation - {st.session_state.get('bien_addr','bien')}.pptx")
        generation_report = generate_estimation_pptx(
            est_tpl_path,
            pptx_out,
            mapping,
            chart_image=histo_path,
            image_by_shape=image_by_shape or None,
            strict=strict_mode,
        )
        if validation_result and validation_result.notes:
            for note in validation_result.notes:
                generation_report.add_note(note)
        generation_report.merge(run_report)
        if strict_mode and validation_result and validation_result.severity == "KO":
            st.error("Génération bloquée : le template n'est pas valide en mode strict.")
        elif strict_mode and not generation_report.ok:
            st.error("Génération interrompue : le rapport signale des éléments bloquants.")
        else:
            st.success(f"OK: {pptx_out}")
            with open(pptx_out, "rb") as f:
                st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))
        render_generation_report(generation_report, strict=strict_mode)

    # =====================================================
    # =============== MANDAT PAGE =========================
    # =====================================================
