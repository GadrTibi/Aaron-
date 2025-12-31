from __future__ import annotations

from typing import Iterable


def _normalize_allowlist(allowlist: Iterable[str] | None) -> set[str]:
    return {tok for tok in (allowlist or []) if isinstance(tok, str)}


def audit_template_tokens(
    template_tokens: set[str],
    mapping: dict[str, str],
    *,
    allowlist: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Compare les tokens du template avec le mapping fourni.

    Retourne un dictionnaire contenant :
    - missing_in_mapping : tokens présents dans le template mais absents du mapping.
    - empty_values : tokens présents dans le template mais dont la valeur est vide.
    - ok : tokens présents et non vides.
    """

    allowed = _normalize_allowlist(allowlist)
    filtered_tokens = {tok for tok in template_tokens if tok not in allowed}

    missing = sorted(filtered_tokens - set(mapping.keys()))
    empty_vals = sorted(
        [
            tok
            for tok in filtered_tokens
            if tok in mapping and isinstance(mapping[tok], str) and mapping[tok].strip() == ""
        ]
    )
    ok = sorted(
        [
            tok
            for tok in filtered_tokens
            if tok in mapping and isinstance(mapping[tok], str) and mapping[tok].strip() != ""
        ]
    )
    return {
        "missing_in_mapping": missing,
        "empty_values": empty_vals,
        "ok": ok,
    }
