from app.services.occupancy_utils import format_days


def test_format_days():
    assert format_days(21.0) == "21"
    assert format_days(24.9) == "24.9"
