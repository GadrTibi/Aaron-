from app.services import quartier_enricher
from app.services.generation_report import GenerationReport
from app.services.text_limits import (
    MAX_QUARTIER_INTRO,
    MAX_TRANSPORT_BUS,
    MAX_TRANSPORT_METRO,
    MAX_TRANSPORT_TAXI,
)


def _build_long_text(length: int) -> str:
    return "x" * length


def test_quartier_enricher_applies_limits(monkeypatch):
    def fake_invoke(prompt, schema, report=None):
        return {
            "quartier_intro": _build_long_text(MAX_QUARTIER_INTRO + 50),
            "transport_metro_texte": _build_long_text(MAX_TRANSPORT_METRO + 50),
            "transport_bus_texte": _build_long_text(MAX_TRANSPORT_BUS + 50),
            "transport_taxi_texte": _build_long_text(MAX_TRANSPORT_TAXI + 50),
        }

    monkeypatch.setattr("app.services.quartier_enricher.invoke_llm_json", fake_invoke)

    report = GenerationReport()
    result = quartier_enricher.enrich_quartier_and_transports("1 rue test", report=report)

    assert len(result["quartier_intro"]) <= MAX_QUARTIER_INTRO
    assert len(result["transport_metro_texte"]) <= MAX_TRANSPORT_METRO
    assert len(result["transport_bus_texte"]) <= MAX_TRANSPORT_BUS
    assert len(result["transport_taxi_texte"]) <= MAX_TRANSPORT_TAXI

    assert any("tronqué" in note for note in report.notes)
