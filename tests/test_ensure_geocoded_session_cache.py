import streamlit as st

from app.services.geo_helpers import ensure_geocoded


def test_ensure_geocoded_session_cache(monkeypatch):
    st.session_state.clear()
    st.session_state["geo_lat"] = 48.1234
    st.session_state["geo_lon"] = 2.9876
    st.session_state["geocoded_address"] = "10 rue test"
    st.session_state["geocode_provider"] = "Nominatim"

    def _fail_fallback(*_args, **_kwargs):
        raise AssertionError("geocode_address_fallback should not be called when session cache matches")

    monkeypatch.setattr("app.services.geo_helpers.geocode_address_fallback", _fail_fallback)

    lat, lon, provider = ensure_geocoded("10 Rue Test")

    assert lat == 48.1234
    assert lon == 2.9876
    assert provider == "session_cache"
