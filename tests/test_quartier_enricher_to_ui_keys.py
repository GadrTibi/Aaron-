import pytest

from app.services.quartier_enricher import enrich_quartier_and_transports


def test_enrich_quartier_maps_to_ui_keys(monkeypatch):
    def fake_invoke(prompt, schema, report=None):
        return {
            "quartier_intro": "Intro",
            "transports_metro_texte": "Legacy Metro",
            "transports_bus_texte": "Legacy Bus",
            "transports_taxi_texte": "Legacy Taxi",
        }

    monkeypatch.setattr("app.services.quartier_enricher.invoke_llm_json", fake_invoke)

    result = enrich_quartier_and_transports("10 rue de test")

    assert result["quartier_intro"] == "Intro"
    assert result["transport_metro_texte"] == "Legacy Metro"
    assert result["transport_bus_texte"] == "Legacy Bus"
    assert result["transport_taxi_texte"] == "Legacy Taxi"
