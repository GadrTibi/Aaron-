import streamlit as st

from app.services.geo_helpers import ensure_geocoded
from app.services.geocode_cache import normalize_address


def test_ensure_geocoded_calls_fallback(monkeypatch):
    st.session_state.clear()

    calls = {}

    def _fake_fallback(address: str, report=None):
        calls["address"] = address
        return 12.34, 56.78, "Geo"

    monkeypatch.setattr("app.services.geo_helpers.geocode_address_fallback", _fake_fallback)

    lat, lon, provider = ensure_geocoded(" 12 rue du Test  ", report=None)

    assert lat == 12.34
    assert lon == 56.78
    assert provider == "Geo"
    assert st.session_state["geo_lat"] == 12.34
    assert st.session_state["geo_lon"] == 56.78
    assert st.session_state["geocode_provider"] == "Geo"
    assert st.session_state["geocoded_address"] == normalize_address("12 rue du Test")
    assert calls["address"] == normalize_address("12 rue du Test")
