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
        "transports_metro_texte": "L1 (Test) - 5min",
        "transports_bus_texte": "Bus 99 - 3min",
        "transports_taxi_texte": "Taxi dispo",
        "metro_lines_auto": [],
        "bus_lines_auto": [],
    })

    monkeypatch.setattr(estimation.st, "session_state", ss.__dict__, raising=False)

    metro = ss.__dict__.get('metro_lines_auto') or []
    bus = ss.__dict__.get('bus_lines_auto') or []
    metro_refs_tokens = estimation._collect_line_refs(metro, limit=3)
    bus_refs_tokens = estimation._collect_line_refs(bus, limit=3)
    metro_str = ", ".join(metro_refs_tokens)
    bus_str = ", ".join(bus_refs_tokens)

    mapping = {
        "[[ADRESSE]]": ss.__dict__.get("bien_addr",""),
        "[[QUARTIER_TEXTE]]": ss.__dict__.get("q_txt",""),
        "[[TRANSPORT_TAXI_TEXTE]]": ss.__dict__.get('q_tx', ''),
        "[[TRANSPORT_METRO_TEXTE]]": metro_str,
        "[[TRANSPORT_BUS_TEXTE]]": bus_str,
        "[[QUARTIER_INTRO]]": ss.__dict__.get("quartier_intro", ""),
        "[[TRANSPORTS_METRO_TEXTE]]": ss.__dict__.get("transports_metro_texte", ""),
        "[[TRANSPORTS_BUS_TEXTE]]": ss.__dict__.get("transports_bus_texte", ""),
        "[[TRANSPORTS_TAXI_TEXTE]]": ss.__dict__.get("transports_taxi_texte", ""),
    }

    for token in (
        "[[QUARTIER_INTRO]]",
        "[[TRANSPORTS_METRO_TEXTE]]",
        "[[TRANSPORTS_BUS_TEXTE]]",
        "[[TRANSPORTS_TAXI_TEXTE]]",
    ):
        assert token in mapping
