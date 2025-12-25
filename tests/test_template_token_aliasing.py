from app.services.token_utils import apply_token_aliases


def test_aliases_applied_when_template_uses_legacy_tokens():
    mapping = {"[[TRANSPORTS_METRO_TEXTE]]": "Metro texte"}
    tokens = {"[[METRO_TEXTE]]", "[[TRANSPORTS_METRO_TEXTE]]"}

    applied = apply_token_aliases(mapping, tokens)

    assert mapping["[[METRO_TEXTE]]"] == "Metro texte"
    assert applied == {"[[METRO_TEXTE]]": "[[TRANSPORTS_METRO_TEXTE]]"}


def test_alias_does_not_override_existing_mapping():
    mapping = {
        "[[TRANSPORTS_BUS_TEXTE]]": "Bus texte",
        "[[BUS_TEXTE]]": "Custom bus",
    }
    tokens = {"[[BUS_TEXTE]]", "[[TRANSPORTS_BUS_TEXTE]]"}

    applied = apply_token_aliases(mapping, tokens)

    assert mapping["[[BUS_TEXTE]]"] == "Custom bus"
    assert applied == {}
