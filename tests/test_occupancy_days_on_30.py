from app.services.occupancy_utils import days_occupied_on_30


def test_days_occupied_on_30():
    assert days_occupied_on_30(70) == 21.0
    assert days_occupied_on_30(83) == 24.9
