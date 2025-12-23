from app.services import geocoding_fallback
from app.services.generation_report import GenerationReport


def test_geocode_fallback_geoapify(monkeypatch):
    monkeypatch.setattr(geocoding_fallback, "geocode_nominatim", lambda addr: (None, None))
    monkeypatch.setattr(geocoding_fallback, "_geocode_geoapify", lambda addr, key, http_get: (10.0, 20.0))

    def _fake_resolve(name: str):
        if name == "GEOAPIFY_API_KEY":
            return "token", "env"
        return "", "missing"

    monkeypatch.setattr(geocoding_fallback, "resolve_api_key", _fake_resolve)

    report = GenerationReport()
    lat, lon, provider = geocoding_fallback.geocode_address_fallback("addr", report=report)

    assert (lat, lon) == (10.0, 20.0)
    assert provider == "Geoapify"
    assert any("Fallback géocodage" in warn for warn in report.provider_warnings)
