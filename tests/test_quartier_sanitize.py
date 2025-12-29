from app.services.quartier_sanitize import sanitize_intro, sanitize_transport_lines


def test_intro_removes_address_and_prefix():
    text = "82 Avenue de Wagram, Paris — Quartier calme avec commerces."
    result = sanitize_intro(text, "82 Avenue de Wagram, Paris")
    assert result.startswith("Dans le 17e arrondissement —")
    assert "82 Avenue de Wagram" not in result


def test_transport_lines_keep_only_matching_patterns():
    metro_text = "Ligne 3 — Station Villiers (5 min à pied)\nMétro proche et commerces"
    bus_text = "Bus 94 — Arrêt Villiers (5 min)\nAutres lignes disponibles"
    sanitized_metro = sanitize_transport_lines(metro_text, "metro")
    sanitized_bus = sanitize_transport_lines(bus_text, "bus")
    assert "commerces" not in sanitized_metro
    assert sanitized_metro.startswith("Ligne 3 — Station Villiers")
    assert "Autres lignes" not in sanitized_bus
    assert sanitized_bus.startswith("Bus 94 — Arrêt Villiers")


def test_taxi_vague_fallbacks_to_concrete():
    taxi_text = "Disponibilité élevée des taxis"
    sanitized = sanitize_transport_lines(taxi_text, "taxi")
    assert sanitized == "Taxis: G7/Uber disponibles (2–5 min)"
