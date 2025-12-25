import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.views.estimation as estimation


def test_mapping_contains_quartier_tokens(monkeypatch):
    ss = types.SimpleNamespace(**{
        "bien_addr": "1 rue Test",
        "quartier_intro": "Intro courte",
        "transport_metro_texte": "L1 (Test) - 5min",
        "transport_bus_texte": "Bus 99 - 3min",
        "transport_taxi_texte": "Taxi dispo",
    })

    monkeypatch.setattr(estimation.st, "session_state", ss.__dict__, raising=False)

    mapping = estimation.build_quartier_transport_tokens_mapping(ss.__dict__)

    for token in (
        "[[QUARTIER_INTRO]]",
        "[[TRANSPORT_METRO_TEXTE]]",
        "[[TRANSPORT_BUS_TEXTE]]",
        "[[TRANSPORT_TAXI_TEXTE]]",
    ):
        assert token in mapping
