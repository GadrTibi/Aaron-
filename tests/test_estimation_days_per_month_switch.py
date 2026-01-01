import pytest

from app.services.revenue import (
    ESTIMATION_DAYS_PER_MONTH_CD,
    ESTIMATION_DAYS_PER_MONTH_MD,
    RevenueInputs,
    compute_revenue,
)


@pytest.mark.parametrize(
    "estimation_type, days_per_month",
    [
        ("CD", ESTIMATION_DAYS_PER_MONTH_CD),
        ("MD", ESTIMATION_DAYS_PER_MONTH_MD),
    ],
)
def test_days_per_month_applies_to_revenue(estimation_type, days_per_month):
    base_price = 100.0
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=base_price,
            taux_occupation_pct=100.0,
            platform_fee_pct=0.0,
            mfy_commission_pct=0.0,
            frais_menage_mensuels=0.0,
        ),
        days_per_month=days_per_month,
    )

    assert calc["jours_occupes"] == pytest.approx(days_per_month)
    assert calc["revenu_brut"] == pytest.approx(base_price * days_per_month)
