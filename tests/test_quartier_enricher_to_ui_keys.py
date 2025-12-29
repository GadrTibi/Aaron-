import pytest

from app.services.quartier_enricher import enrich_quartier_and_transports


def test_enrich_quartier_maps_to_ui_keys(monkeypatch):
    def fake_invoke(prompt, schema, report=None):
        return {
            "quartier_intro": "Quartier Monceau (17e) — Calme et haussmannien.",
            "transports_metro_texte": "Ligne 2 — Station Monceau (8 min à pied)",
            "transports_bus_texte": "Bus 30 — Arrêt Monceau (3 min)",
            "transports_taxi_texte": "Station de taxis Monceau (5 min à pied)",
        }

    monkeypatch.setattr("app.services.quartier_enricher.invoke_llm_json", fake_invoke)

    result = enrich_quartier_and_transports("10 rue de test")

    assert result["quartier_intro"].startswith("Quartier Monceau")
    assert result["transport_metro_texte"] == "Métro, ligne 2"
    assert result["transport_bus_texte"] == "Bus, ligne 30"
    assert result["transport_taxi_texte"] == "Stations de taxi"
