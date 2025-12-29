from app.services.transports_compact import (
    build_compact_transport_texts,
    extract_bus_lines,
    extract_metro_lines,
    format_compact_lines,
)


def test_extract_metro_lines_filters_minutes_and_keeps_order():
    metro_raw = "Ligne 3 (Station Villiers) - 5min. Ligne 2 - 8min"
    assert extract_metro_lines(metro_raw) == ["3", "2"]


def test_extract_metro_lines_supports_bis():
    metro_raw = "3 bis, 7bis, Ligne 12"
    assert extract_metro_lines(metro_raw) == ["3bis", "7bis", "12"]


def test_extract_bus_lines_skips_minutes_and_deduplicates():
    bus_raw = "Bus 30 — arrêt X. Bus 94 — arrêt Y. Lignes 31 et 54"
    assert extract_bus_lines(bus_raw) == ["30", "94", "31", "54"]


def test_format_compact_lines_handles_overflow():
    lines = ["1", "2", "3", "4", "5"]
    assert format_compact_lines("Métro, ligne", lines, max_items=4) == "Métro, ligne 1, 2, 3, 4…"


def test_build_compact_transport_texts_applies_fallbacks():
    formatted = build_compact_transport_texts("1, 2, 3, 4, 5", "10, 20, 30, 40, 50, 60, 70", "")
    assert formatted["transport_metro_texte"] == "Métro, ligne 1, 2, 3, 4…"
    assert formatted["transport_bus_texte"] == "Bus, ligne 10, 20, 30, 40, 50, 60…"
    assert formatted["transport_taxi_texte"] == "Stations de taxi"
