from __future__ import annotations

from typing import Dict

import streamlit as st

from services.places_geoapify import GeoapifyPlacesService, Place


def _build_mapping() -> Dict[str, str]:
    return {
        "[[INCONTOURNABLE_1_NOM]]": st.session_state.get("i1", ""),
        "[[INCONTOURNABLE_2_NOM]]": st.session_state.get("i2", ""),
        "[[INCONTOURNABLE_3_NOM]]": st.session_state.get("i3", ""),
    }


def _deduplicate_places(places: list[Place]) -> list[Place]:
    deduped: list[Place] = []
    seen: set[tuple[str, float, float]] = set()
    for place in places:
        key = (place.name, round(place.lat, 6), round(place.lon, 6))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(place)
    return deduped


def render_incontournables_geoapify(config, lat: float, lon: float) -> Dict[str, str]:
    """Render the Geoapify incontournables section and return PPTX mapping."""

    _ = config  # currently unused but kept for signature compatibility
    radius_m = int(st.session_state.get("radius_m", 1200))
    mapping = _build_mapping()

    if lat is None or lon is None:
        st.info("Adresse géocodée requise pour charger les incontournables.")
        return mapping

    try:
        service = GeoapifyPlacesService()
    except ValueError:
        st.warning("Clé Geoapify manquante (GEOAPIFY_API_KEY).")
        return {
            "[[INCONTOURNABLE_1_NOM]]": "",
            "[[INCONTOURNABLE_2_NOM]]": "",
            "[[INCONTOURNABLE_3_NOM]]": "",
        }

    try:
        places = service.list_incontournables(lat, lon, radius_m, limit=15)
    except Exception:
        st.warning("Erreur Geoapify, réessayez plus tard.")
        return mapping

    places = _deduplicate_places(places)[:15]
    st.caption(f"Rayon: {radius_m} m — {len(places)} propositions (source: Geoapify)")

    if not places:
        st.info("Aucune proposition Geoapify pour cette zone.")
        return mapping

    for place in places:
        st.write(f"• {place.name} — {round(place.distance_m)} m")

    options = [place.name for place in places]
    default_selection = [
        value
        for value in (
            st.session_state.get("i1", ""),
            st.session_state.get("i2", ""),
            st.session_state.get("i3", ""),
        )
        if value and value in options
    ]

    multiselect_args = {
        "label": "Incontournables (max 3)",
        "options": options,
        "default": default_selection,
    }
    try:
        selections = st.multiselect(max_selections=3, **multiselect_args)
    except TypeError:
        selections = st.multiselect(**multiselect_args)

    if len(selections) > 3:
        st.warning("Limite: 3 éléments maximum.")
        selections = selections[:3]

    selections += [""] * (3 - len(selections))
    st.session_state["i1"], st.session_state["i2"], st.session_state["i3"] = selections

    return _build_mapping()
