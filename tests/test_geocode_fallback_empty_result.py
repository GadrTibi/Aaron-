from app.services import geocoding_fallback
from app.services.generation_report import GenerationReport


def test_geocode_fallback_empties_trigger_next_provider(monkeypatch):
    called = {"geoapify": False}

    monkeypatch.setattr(
        geocoding_fallback,
        "geocode_nominatim",
        lambda addr, **kwargs: (None, None),
    )
    monkeypatch.setattr(
        geocoding_fallback,
        "_geocode_geoapify",
        lambda addr, key, http_get: called.__setitem__("geoapify", True) or (42.0, 2.0),
    )

    def _fake_resolve(name: str):
        if name == "GEOAPIFY_API_KEY":
            return "token", "env"
        return "", "missing"

    monkeypatch.setattr(geocoding_fallback, "resolve_api_key", _fake_resolve)

    report = GenerationReport()
    lat, lon, provider = geocoding_fallback.geocode_address_fallback("10 rue test", report=report)

    assert (lat, lon) == (42.0, 2.0)
    assert provider == "Geoapify"
    assert called["geoapify"] is True
    assert any("Nominatim n'a retourné aucun résultat." in warn for warn in report.provider_warnings)
