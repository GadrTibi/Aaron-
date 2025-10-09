"""Streamlit section dedicated to the "Incontournables" selection."""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

import streamlit as st

from services.wiki_poi import POI, WikiPOIService


_RADIUS_CHOICES: Sequence[Tuple[str, int]] = (
    ("800 m", 800),
    ("1200 m", 1200),
    ("2000 m", 2000),
)


def _empty_mapping() -> Dict[str, str]:
    return {
        "[[INCONTOURNABLE_1_NOM]]": "",
        "[[INCONTOURNABLE_2_NOM]]": "",
        "[[INCONTOURNABLE_3_NOM]]": "",
    }


def _format_distance(distance_m: float) -> str:
    return f"{round(distance_m):,}".replace(",", " ") + " m"


def _serialize_pois(items: Iterable[POI]) -> List[Dict[str, object]]:
    seen: set[Tuple[str, float, float]] = set()
    results: List[Dict[str, object]] = []
    for poi in items:
        key = (poi.name_display.strip(), round(poi.lat, 6), round(poi.lon, 6))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "name": poi.name_display,
                "full": poi.name_full or "",
                "distance_m": float(poi.distance_m),
                "distance_label": _format_distance(float(poi.distance_m)),
            }
        )
        if len(results) >= 15:
            break
    return results


def _fetch_incontournables(lat: float, lon: float, radius_m: int) -> List[Dict[str, object]]:
    service = WikiPOIService()
    categories = service.list_by_category(lat, lon, radius_m)
    items = categories.get("incontournables", [])
    return _serialize_pois(items)


def render_incontournables_section(config, lat: float | None, lon: float | None) -> Dict[str, str]:
    """Render the Incontournables UI and return the PPTX mapping subset."""

    _ = config  # kept for signature stability / future use

    mapping = _empty_mapping()
    current_radius = int(st.session_state.get("radius_m", 1200))
    labels = [label for label, _ in _RADIUS_CHOICES]
    value_map = {label: radius for label, radius in _RADIUS_CHOICES}
    default_label = next((label for label, radius in _RADIUS_CHOICES if radius == current_radius), "1200 m")
    try:
        default_index = labels.index(default_label)
    except ValueError:
        default_index = labels.index("1200 m")

    selected_label = st.selectbox(
        "Rayon de recherche",
        labels,
        index=default_index,
        key="incontournables_radius_label",
    )
    radius_m = value_map[selected_label]
    if radius_m != current_radius:
        st.session_state["radius_m"] = radius_m

    cache_key: Tuple[float, float, int] | None = None
    if lat is not None and lon is not None:
        cache_key = (round(lat, 5), round(lon, 5), radius_m)

    cache_store: Dict[Tuple[float, float, int], List[Dict[str, object]]] = st.session_state.setdefault(
        "_incontournables_cache", {}
    )

    load_disabled = cache_key is None
    if load_disabled:
        st.caption("Géocodez l'adresse principale pour activer la recherche d'incontournables.")

    items: List[Dict[str, object]] = st.session_state.get("incontournables_items", [])
    cache_message = ""
    if st.button("Charger les incontournables", disabled=load_disabled):
        if cache_key is None:
            st.warning("Adresse introuvable. Lancez d'abord la géolocalisation.")
        else:
            try:
                if cache_key in cache_store:
                    items = cache_store[cache_key]
                    cache_message = "Résultats issus du cache (session)."
                else:
                    with st.spinner("Chargement des incontournables…"):
                        items = _fetch_incontournables(lat, lon, radius_m)
                    cache_store[cache_key] = items
                    cache_message = "Résultats rafraîchis depuis Wikipedia/Wikidata."
            except Exception as exc:  # pragma: no cover - defensive UI path
                st.warning(f"Incontournables indisponibles: {exc}")
                st.session_state["incontournables_items"] = []
                st.session_state.pop("_incontournables_last_key", None)
                return mapping
            st.session_state["incontournables_items"] = items
            st.session_state["_incontournables_last_key"] = cache_key

    if cache_message:
        st.caption(cache_message)

    if not items:
        st.info("Aucun résultat à ce périmètre. Essayez d'augmenter le rayon.")
    else:
        for entry in items:
            name = str(entry.get("name", ""))
            distance_label = str(entry.get("distance_label", ""))
            st.markdown(f"**{name}** — {distance_label}")
            full = str(entry.get("full", "")).strip()
            if full and full != name:
                st.caption(full)

    default_selection = [
        value
        for value in (
            st.session_state.get("i1"),
            st.session_state.get("i2"),
            st.session_state.get("i3"),
        )
        if value
    ]
    options = [str(entry.get("name", "")) for entry in items]
    selected = st.multiselect(
        "Sélection d'incontournables (max 3)",
        options=options,
        default=[value for value in default_selection if value in options] or options[:3],
        max_selections=3,
        key="incontournables_selection",
    )

    if len(selected) > 3:
        st.warning("Limite: 3 éléments maximum.")
        selected = selected[:3]

    st.session_state["i1"] = selected[0] if len(selected) > 0 else ""
    st.session_state["i2"] = selected[1] if len(selected) > 1 else ""
    st.session_state["i3"] = selected[2] if len(selected) > 2 else ""

    summary_values = [st.session_state.get("i1", ""), st.session_state.get("i2", ""), st.session_state.get("i3", "")]
    summary_parts = [f"{idx}) {value or '—'}" for idx, value in enumerate(summary_values, start=1)]
    st.caption("Choisis : " + "  ".join(summary_parts))
    st.caption("source: Wikipedia/Wikidata")

    mapping.update(
        {
            "[[INCONTOURNABLE_1_NOM]]": summary_values[0],
            "[[INCONTOURNABLE_2_NOM]]": summary_values[1],
            "[[INCONTOURNABLE_3_NOM]]": summary_values[2],
        }
    )
    return mapping
