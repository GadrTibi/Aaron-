import pytest

from app.services import text_constraints


def test_enforce_limits_trims_extra_lines():
    text = "L1 A\nL2 B\nL3 C\nL4 D\nL5 E"
    result = text_constraints.enforce_limits(text, text_constraints.METRO_MAX_CHARS, 3)
    assert result.splitlines() == ["L1 A", "L2 B", "L3 C"]


def test_enforce_limits_truncates_with_ellipsis_when_still_too_long():
    long_line = "L1 " + "X" * 150
    result = text_constraints.enforce_limits(long_line, 20, 3)
    assert result.endswith("…")
    assert len(result) == 20


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("Ligne 3 (Station Villiers) - 5 minutes à pied", "L3 (Villiers) - 5 min"),
        ("Arrêt 42; Station Test: 10 minutes", "42 Test 10 min"),
    ],
)
def test_compact_line_removes_noise(input_text, expected):
    assert text_constraints.compact_line(input_text) == expected
