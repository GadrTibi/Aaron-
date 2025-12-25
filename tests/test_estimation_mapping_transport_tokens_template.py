from app.services.template_tokens import build_quartier_transport_tokens_mapping


def test_mapping_uses_canonical_transport_tokens():
    mapping = build_quartier_transport_tokens_mapping(
        {
            "quartier_intro": "Intro quartier",
            "transport_metro_texte": "Ligne 1 (Test)",
            "transport_bus_texte": "Bus 20 (Test)",
            "transport_taxi_texte": "Taxis disponibles",
        }
    )

    assert mapping["[[QUARTIER_INTRO]]"] == "Intro quartier"
    assert mapping["[[TRANSPORT_METRO_TEXTE]]"] == "Ligne 1 (Test)"
    assert mapping["[[TRANSPORT_BUS_TEXTE]]"] == "Bus 20 (Test)"
    assert mapping["[[TRANSPORT_TAXI_TEXTE]]"] == "Taxis disponibles"


def test_mapping_mirrors_quartier_intro_to_optional_quartier_texte():
    mapping = build_quartier_transport_tokens_mapping(
        {
            "quartier_intro": "Intro quartier",
            "transport_metro_texte": "",
            "transport_bus_texte": "",
            "transport_taxi_texte": "",
        }
    )

    assert mapping["[[QUARTIER_TEXTE]]"] == "Intro quartier"
