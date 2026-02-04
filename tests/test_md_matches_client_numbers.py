from app.services.revenue import RevenueInputs, compute_revenue, round_to_50_down


def test_md_matches_client_numbers():
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=126,
            taux_occupation_pct=0.0,
            platform_fee_pct=15.0,
            mfy_commission_pct=15.0,
        ),
        estimation_type="MD",
    )

    base_estimation = calc["base_estimation"]
    prix_pess = round_to_50_down(base_estimation * 0.93)
    prix_cible = round_to_50_down(base_estimation * 1.00)
    prix_opt = round_to_50_down(base_estimation * 1.06)

    assert calc["revenu_brut"] == 3276
    assert calc["platform_fee_eur"] == 491
    assert calc["mfy_commission_eur"] == 418
    assert calc["frais_generaux"] == 909
    assert prix_pess == 2200
    assert prix_cible == 2350
    assert prix_opt == 2500
