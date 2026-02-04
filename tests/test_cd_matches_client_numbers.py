from app.services.revenue import RevenueInputs, compute_revenue, round_to_50


def test_cd_matches_client_numbers():
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=179.0,
            taux_occupation_pct=85.0,
            platform_fee_pct=15.0,
            mfy_commission_pct=15.0,
        ),
        days_per_month=30.46,
    )

    assert calc["revenu_brut"] == 4634
    assert calc["platform_fee_eur"] == 695
    assert calc["mfy_commission_eur"] == 591
    assert calc["frais_generaux"] == 1286

    base_estimation = calc["base_estimation"]
    assert round_to_50(base_estimation * 1.0) == 3350
    assert round_to_50(base_estimation * 0.88) == 2950
    assert round_to_50(base_estimation * 1.15) == 3850


def test_round_to_50():
    assert round_to_50(3348) == 3350
    assert round_to_50(2946) == 2950
    assert round_to_50(3850.2) == 3850
