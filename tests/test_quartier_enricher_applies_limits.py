from app.services.generation_report import GenerationReport
from app.services.quartier_enricher import QuartierEnricher
from app.services.text_constraints import (
    BUS_MAX_CHARS,
    BUS_MAX_LINES,
    METRO_MAX_CHARS,
    METRO_MAX_LINES,
    TAXI_MAX_CHARS,
    TAXI_MAX_LINES,
)


def test_quartier_enricher_applies_limits_and_notes():
    captured = {}

    def fake_llm(prompt: str):
        captured["prompt"] = prompt
        return {
            "transport_metro_texte": "\n".join(
                [
                    "Ligne 1 Station Très Longue – 10 minutes à pied",
                    "Ligne 2 Station Très Longue – 9 minutes à pied",
                    "Ligne 3 Station Très Longue – 8 minutes à pied",
                    "Ligne 4 Station Très Longue – 7 minutes à pied",
                ]
            ),
            "transport_bus_texte": "\n".join(
                [
                    "Bus 30 Vers Villiers – 2 minutes à pied",
                    "Bus 43 Vers Villiers – 3 minutes à pied",
                    "Bus 84 Vers Ternes – 6 minutes à pied",
                    "Bus 92 Vers Trocadéro – 10 minutes à pied",
                ]
            ),
            "transport_taxi_texte": "Station de taxi disponible en 12 minutes à pied près de la place centrale",
        }

    enricher = QuartierEnricher(fake_llm)
    report = GenerationReport()
    enriched, final_report = enricher.enrich({"adresse": "Test"}, report=report)

    assert len(enriched["transport_metro_texte"]) <= METRO_MAX_CHARS
    assert len(enriched["transport_metro_texte"].splitlines()) <= METRO_MAX_LINES
    assert len(enriched["transport_bus_texte"]) <= BUS_MAX_CHARS
    assert len(enriched["transport_bus_texte"].splitlines()) <= BUS_MAX_LINES
    assert len(enriched["transport_taxi_texte"]) <= TAXI_MAX_CHARS
    assert len(enriched["transport_taxi_texte"].splitlines()) <= TAXI_MAX_LINES

    assert any("Metro trimmed" in note for note in final_report.notes)
    assert any("Bus trimmed" in note for note in final_report.notes)
    assert any("Taxi trimmed" in note for note in final_report.notes)

    prompt = captured["prompt"].lower()
    assert "pas de phrases explicatives" in prompt
    assert "l3 villiers" in prompt
