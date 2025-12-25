import requests

from app.services.generation_report import GenerationReport
import app.services.transports_facade as facade


def test_overpass_timeout_returns_warning(monkeypatch):
    def fake_query(query):
        raise requests.Timeout()

    monkeypatch.setattr(facade, "_query_overpass_points", fake_query)
    facade.clear_transport_cache()
    report = GenerationReport()

    result = facade.get_transports(48.0, 2.0, radius_m=800, mode="FAST", report=report)

    assert result["metro_lines"] == []
    assert result["bus_lines"] == []
    assert any("timeout" in warning.lower() for warning in report.provider_warnings)
