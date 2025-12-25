from app.services.template_tokens import migrate_quartier_transport_session


def test_migrate_quartier_transport_session_copies_legacy_once():
    state = {
        "quartier_intro": "Intro",
        "transports_metro_texte": "Metro legacy",
        "transports_bus_texte": "Bus legacy",
        "transports_taxi_texte": "Taxi legacy",
    }

    migrate_quartier_transport_session(state)

    assert state["transport_metro_texte"] == "Metro legacy"
    assert state["transport_bus_texte"] == "Bus legacy"
    assert state["transport_taxi_texte"] == "Taxi legacy"
    # Anciennes clés conservées pour compat éventuelle
    assert state["transports_metro_texte"] == "Metro legacy"
