import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.token_aliases import apply_token_aliases


def test_apply_token_aliases_adds_missing_aliases():
    mapping = {"[[TRANSPORTS_METRO_TEXTE]]": "M1"}

    result = apply_token_aliases(mapping)

    assert result["[[TRANSPORTS_METRO_TEXTE]]"] == "M1"
    assert result["[[TRANSPORT_METRO_TEXTE]]"] == "M1"
    assert "[[TRANSPORT_METRO_TEXTE]]" not in mapping


def test_apply_token_aliases_preserves_existing_values():
    mapping = {
        "[[TRANSPORTS_BUS_TEXTE]]": "Bus canonical",
        "[[TRANSPORT_BUS_TEXTE]]": "Custom alias",
    }

    result = apply_token_aliases(mapping)

    assert result["[[TRANSPORTS_BUS_TEXTE]]"] == "Bus canonical"
    assert result["[[TRANSPORT_BUS_TEXTE]]"] == "Custom alias"


def test_apply_token_aliases_backfills_canonical_from_alias():
    mapping = {"[[TRANSPORT_TAXI_TEXTE]]": "Taxi alias only"}

    result = apply_token_aliases(mapping)

    assert result["[[TRANSPORT_TAXI_TEXTE]]"] == "Taxi alias only"
    assert result["[[TRANSPORTS_TAXI_TEXTE]]"] == "Taxi alias only"
