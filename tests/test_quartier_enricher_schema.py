import pytest

from app.services.quartier_enricher import enrich_quartier_and_transports


def test_enrich_quartier_and_transports_returns_fields(monkeypatch):
    called = {}

    def fake_invoke(prompt, schema, report=None):
        called["prompt"] = prompt
        called["schema"] = schema
        return {
            "quartier_intro": "Quartier Batignolles (17e) — Ambiance conviviale et commerces de proximité.",
            "transport_metro_texte": "Ligne 1 — Station Bastille (5 min à pied)\nLigne 3 — Station Bourse (8 min à pied)",
            "transport_bus_texte": "Bus 69 — Arrêt Saint-Paul (3 min)\nBus 94 — Arrêt Villiers (5 min)",
            "transport_taxi_texte": "Station de taxis Villiers (4 min à pied)",
        }

    monkeypatch.setattr("app.services.quartier_enricher.invoke_llm_json", fake_invoke)

    result = enrich_quartier_and_transports("12 rue de Rivoli, Paris")

    assert set(result.keys()) == {
        "quartier_intro",
        "transport_metro_texte",
        "transport_bus_texte",
        "transport_taxi_texte",
    }
    assert "Bastille" in result["transport_metro_texte"]
