from app.services.text_constraints import BUS_MAX_LINES, METRO_MAX_LINES, enforce_limits


def test_enforce_limits_caps_number_of_lines():
    text = "L1\nL2\nL3\nL4\nL5"
    result = enforce_limits(text, max_chars=200, max_lines=METRO_MAX_LINES)
    assert len(result.splitlines()) == METRO_MAX_LINES


def test_enforce_limits_truncates_with_ellipsis():
    text = "12345678901234567890"
    result = enforce_limits(text, max_chars=10, max_lines=1)
    assert result.endswith("…")
    assert len(result) == 10


def test_compact_line_shortens_common_patterns():
    text = "Ligne 3 (Station Villiers) - 5min à pied"
    result = enforce_limits(text, max_chars=50, max_lines=1)
    assert result == "L3 Villiers - 5min"


def test_enforce_limits_prefers_fewer_lines_before_truncating():
    text = "Bus 30 Villiers - 2 minutes\nBus 31 Villiers - 3 minutes\nBus 43 Villiers - 4 minutes\nBus 90 Longlabel"
    result = enforce_limits(text, max_chars=60, max_lines=BUS_MAX_LINES)
    assert len(result.splitlines()) <= BUS_MAX_LINES
    assert len(result) <= 60
