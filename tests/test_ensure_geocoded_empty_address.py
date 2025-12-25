import pytest
import streamlit as st

from app.services.geo_helpers import ensure_geocoded


def test_ensure_geocoded_empty_address():
    st.session_state.clear()
    with pytest.raises(ValueError):
        ensure_geocoded("   ")
