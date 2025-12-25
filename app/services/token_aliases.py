from __future__ import annotations

from typing import Dict

TOKEN_ALIASES: Dict[str, list[str]] = {
    "[[TRANSPORTS_METRO_TEXTE]]": ["[[TRANSPORT_METRO_TEXTE]]"],
    "[[TRANSPORTS_BUS_TEXTE]]": ["[[TRANSPORT_BUS_TEXTE]]"],
    "[[TRANSPORTS_TAXI_TEXTE]]": ["[[TRANSPORT_TAXI_TEXTE]]"],
    "[[QUARTIER_TEXTE]]": ["[[QUARTIER_INTRO]]"],
}


def apply_token_aliases(mapping: Dict[str, str]) -> Dict[str, str]:
    """
    Add aliases for known tokens without overwriting existing values.

    For each canonical token and its aliases, the first available value is
    propagated to the missing keys. Existing keys are preserved.
    """
    result: Dict[str, str] = dict(mapping)
    for canonical, aliases in TOKEN_ALIASES.items():
        tokens = [canonical, *aliases]
        source_value = None
        for token in tokens:
            if token in result:
                source_value = result[token]
                break
        if source_value is None:
            continue
        for token in tokens:
            if token not in result:
                result[token] = source_value
    return result
