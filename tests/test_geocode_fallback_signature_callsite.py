import pytest

from app.services import geocoding_fallback
from app.services.generation_report import GenerationReport


def test_geocode_fallback_returns_three_values(monkeypatch):
    monkeypatch.setattr(
        geocoding_fallback,
        "geocode_nominatim",
        lambda addr, **kwargs: (1.0, 2.0),
    )

    report = GenerationReport()
    result = geocoding_fallback.geocode_address_fallback("adresse test", report=report)

    assert isinstance(result, tuple)
    assert len(result) == 3
    lat, lon, provider = result
    assert (lat, lon, provider) == (1.0, 2.0, "Nominatim")


def test_geocode_fallback_rejects_empty_addresses():
    with pytest.raises(ValueError):
        geocoding_fallback.geocode_address_fallback("   ")
