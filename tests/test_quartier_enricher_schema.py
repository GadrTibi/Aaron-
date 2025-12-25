import pytest

from app.services.quartier_enricher import enrich_quartier_and_transports


def test_enrich_quartier_and_transports_returns_fields(monkeypatch):
    called = {}

    def fake_invoke(prompt, schema, report=None):
        called["prompt"] = prompt
        called["schema"] = schema
        return {
            "quartier_intro": "Quartier vivant et culturel.",
            "transports_metro_texte": "Ligne 1 (Bastille) - 5min à pied",
            "transports_bus_texte": "Bus 69 (Saint-Paul) - 3min",
            "transports_taxi_texte": "Stations taxis à 2min",
        }

    monkeypatch.setattr("app.services.quartier_enricher.invoke_llm_json", fake_invoke)

    result = enrich_quartier_and_transports("12 rue de Rivoli, Paris")

    assert set(result.keys()) == {
        "quartier_intro",
        "transports_metro_texte",
        "transports_bus_texte",
        "transports_taxi_texte",
    }
    assert "Bastille" in result["transports_metro_texte"]

