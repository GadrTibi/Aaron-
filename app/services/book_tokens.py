"""Mapping helpers for Book PPTX token replacement."""
from __future__ import annotations


def _collect_line_refs(items: list) -> list[str]:
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
    return refs


def build_book_mapping(ss: dict) -> dict:
    """Build token->value mapping for the Book PPTX.

    Parameters
    ----------
    ss: dict
        Usually ``st.session_state``.

    Returns
    -------
    dict
        Mapping suitable for ``replace_text_preserving_style``.
    """

    # Adresse: prioriser 'bien_addr' (provenant de Données générales)
    adresse = ss.get("bien_addr") or ss.get("bk_adresse") or ""

    # Transports: reprendre ceux de la session (Estimation)
    metro_auto = ss.get('metro_lines_auto') or []
    bus_auto = ss.get('bus_lines_auto') or []
    taxi_txt = ss.get('q_tx', "")

    metro_refs = _collect_line_refs(metro_auto)
    bus_refs = _collect_line_refs(bus_auto)
    metro_str = ", ".join(metro_refs)
    bus_str = ", ".join(bus_refs)

    mapping = {
        # Adresse/Transports (Slide 4)
        "[[ADRESSE]]": adresse,
        "[[BOOK_ADRESSE]]": adresse,

        # Convention “Estimation” pour les transports
        "[[TRANSPORT_TAXI_TEXTE]]": taxi_txt,
        "[[TRANSPORT_METRO_TEXTE]]": metro_str,
        "[[TRANSPORT_BUS_TEXTE]]": bus_str,

        # Compatibilité alternative (si le template Book utilise ces noms)
        "[[TAXI_TEXTE]]": taxi_txt,
        "[[TRANSPORT_METRO_TEXTE]]": metro_str,
        "[[TRANSPORT_BUS_TEXTE]]": bus_str,

        # Slide 5 (Instructions)
        "[[PORTE_ENTREE_TEXTE]]": ss.get("bk_porte_entree_texte", ""),
        "[[ENTREE_TEXTE]]": ss.get("bk_entree_texte", ""),
        "[[APPARTEMENT_TEXTE]]": ss.get("bk_appartement_texte", ""),
        # Anciennes conventions (pour compatibilité éventuelle)
        "[[BOOK_ACC_PORTE_TEXTE]]": ss.get("bk_porte_entree_texte", ""),
        "[[BOOK_ACC_ENTREE_TEXTE]]": ss.get("bk_entree_texte", ""),
        "[[BOOK_ACC_APPART_TEXTE]]": ss.get("bk_appartement_texte", ""),

        # Slide 8 (Wifi)
        "[[NETWORK_NAME]]": ss.get("bk_network_name", ""),
        "[[NETWORK_PASSWORD]]": ss.get("bk_network_password", ""),
        # Anciennes conventions
        "[[WIFI_NETWORK_NAME]]": ss.get("bk_network_name", ""),
        "[[WIFI_PASSWORD]]": ss.get("bk_network_password", ""),
    }
    return mapping
