import pytest

from app.services import text_constraints
from app.services.generation_report import GenerationReport
from app.services.quartier_enricher import enrich_quartier_and_transports


def test_enrich_quartier_applies_limits(monkeypatch):
    long_metro = "L1 " + "X" * 200
    long_bus = "Bus 30 " + "Y" * 200
    long_taxi = "Taxi " + "Z" * 200

    def fake_invoke(prompt, schema, report=None):
        return {
            "quartier_intro": "Intro",
            "transport_metro_texte": long_metro,
            "transport_bus_texte": long_bus,
            "transport_taxi_texte": long_taxi,
        }

    monkeypatch.setattr("app.services.quartier_enricher.invoke_llm_json", fake_invoke)

    report = GenerationReport()
    result = enrich_quartier_and_transports("10 rue de test", report)

    assert len(result["transport_metro_texte"]) <= text_constraints.METRO_MAX_CHARS
    assert len(result["transport_bus_texte"]) <= text_constraints.BUS_MAX_CHARS
    assert len(result["transport_taxi_texte"]) <= text_constraints.TAXI_MAX_CHARS

    assert len(result["transport_metro_texte"].splitlines()) <= text_constraints.METRO_MAX_LINES
    assert len(result["transport_bus_texte"].splitlines()) <= text_constraints.BUS_MAX_LINES
    assert len(result["transport_taxi_texte"].splitlines()) <= text_constraints.TAXI_MAX_LINES

    assert any(note.startswith("Metro trimmed") for note in report.notes)
    assert any(note.startswith("Bus trimmed") for note in report.notes)
    assert any(note.startswith("Taxi trimmed") for note in report.notes)
