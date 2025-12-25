from app.views.utils import apply_pending_fields


def test_apply_pending_fields_applies_and_clears():
    state = {
        "quartier_intro": "Ancienne intro",
        "_quartier_pending": {
            "quartier_intro": "Nouvelle intro",
            "transports_bus_texte": "Bus à jour",
        },
    }

    applied = apply_pending_fields(
        state,
        "_quartier_pending",
        ("quartier_intro", "transports_metro_texte", "transports_bus_texte", "transports_taxi_texte"),
    )

    assert applied is True
    assert state["quartier_intro"] == "Nouvelle intro"
    assert state["transports_bus_texte"] == "Bus à jour"
    assert "_quartier_pending" not in state


def test_apply_pending_fields_no_pending_returns_false():
    state = {"quartier_intro": "Intro existante"}

    applied = apply_pending_fields(
        state,
        "_quartier_pending",
        ("quartier_intro", "transports_metro_texte", "transports_bus_texte", "transports_taxi_texte"),
    )

    assert applied is False
    assert state["quartier_intro"] == "Intro existante"
