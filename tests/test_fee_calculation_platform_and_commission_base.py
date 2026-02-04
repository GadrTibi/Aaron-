import pytest

from app.services.revenue import RevenueInputs, compute_revenue


def test_platform_fee_and_commission_base():
    inputs = RevenueInputs(
        prix_nuitee=1000 / 30,
        taux_occupation_pct=100,
        platform_fee_pct=10,
        mfy_commission_pct=20,
    )

    result = compute_revenue(inputs)

    assert result["revenu_brut"] == pytest.approx(1000)
    assert result["platform_fee_eur"] == 100
    assert result["base_commission"] == pytest.approx(900)
    assert result["mfy_commission_eur"] == 180
