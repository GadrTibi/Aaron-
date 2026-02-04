import pytest

from app.services.revenue import (
    ESTIMATION_DAYS_PER_MONTH_CD,
    ESTIMATION_DAYS_PER_MONTH_MD,
    RevenueInputs,
    compute_prix_cible,
    compute_revenue,
)


@pytest.mark.parametrize(
    "days_per_month",
    [ESTIMATION_DAYS_PER_MONTH_CD, ESTIMATION_DAYS_PER_MONTH_MD],
)
def test_frais_generaux_is_platform_plus_commission(days_per_month):
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=100.0,
            taux_occupation_pct=80.0,
            platform_fee_pct=12.5,
            mfy_commission_pct=20.0,
        ),
        days_per_month=days_per_month,
    )

    assert calc["frais_generaux"] == calc["platform_fee_eur"] + calc["mfy_commission_eur"]


@pytest.mark.parametrize(
    "days_per_month",
    [ESTIMATION_DAYS_PER_MONTH_CD, ESTIMATION_DAYS_PER_MONTH_MD],
)
def test_prix_cible_is_based_on_brut_minus_platform_and_commission(days_per_month):
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=120.0,
            taux_occupation_pct=75.0,
            platform_fee_pct=10.0,
            mfy_commission_pct=15.0,
        ),
        days_per_month=days_per_month,
    )

    prix_cible = compute_prix_cible(
        calc["revenu_brut"],
        calc["platform_fee_eur"],
        calc["mfy_commission_eur"],
    )

    assert prix_cible == calc["revenu_brut"] - calc["platform_fee_eur"] - calc["mfy_commission_eur"]
