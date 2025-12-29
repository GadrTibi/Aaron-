from app.services.quartier_sanitize import sanitize_transport_lines


def test_metro_truncated_to_three_lines():
    metro_text = "\n".join(
        [
            "Ligne 1 — Station A (5 min)",
            "Ligne 2 — Station B (6 min)",
            "Ligne 3 — Station C (4 min)",
            "Ligne 4 — Station D (7 min)",
            "Ligne 5 — Station E (8 min)",
        ]
    )
    sanitized = sanitize_transport_lines(metro_text, "metro")
    lines = sanitized.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("Ligne 1")
    assert lines[-1].startswith("Ligne 3")


def test_bus_split_on_punctuation_and_truncated():
    bus_text = "Bus 30 — Arrêt Alpha (2 min). Bus 38 — Arrêt Beta (4 min). Bus 95 — Arrêt Gamma (6 min). Bus 84 — Arrêt Delta (8 min)"
    sanitized = sanitize_transport_lines(bus_text, "bus")
    lines = sanitized.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("Bus 30")
    assert lines[-1].startswith("Bus 95")


def test_non_matching_phrases_are_removed():
    mixed_text = "Bus 94 — Arrêt Villiers (5 min); Autres bus disponibles; Bus 21 — Arrêt Rome (6 min)"
    sanitized = sanitize_transport_lines(mixed_text, "bus")
    lines = sanitized.splitlines()
    assert len(lines) == 2
    assert all("Autres bus" not in line for line in lines)
