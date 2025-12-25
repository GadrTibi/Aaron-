import types

import app.views.estimation as estimation


def test_transport_mapping_contains_expected_tokens(monkeypatch):
    ss = types.SimpleNamespace(
        quartier_intro="Intro courte",
        transports_metro_texte="L1 (Test) - 5min",
        transports_bus_texte="Bus 99 - 3min",
        transports_taxi_texte="Taxi dispo",
        metro_lines_auto=["M1", "M2"],
        bus_lines_auto=["B1"],
    )
    monkeypatch.setattr(estimation.st, "session_state", ss.__dict__, raising=False)

    mapping = estimation.build_transport_mapping(estimation.st.session_state)

    for token in estimation.CRITICAL_TRANSPORT_TOKENS:
        assert token in mapping

    assert mapping["[[TRANSPORTS_METRO_TEXTE]]"] == "L1 (Test) - 5min"
    assert mapping["[[TRANSPORTS_BUS_TEXTE]]"] == "Bus 99 - 3min"
    assert mapping["[[TRANSPORTS_TAXI_TEXTE]]"] == "Taxi dispo"
