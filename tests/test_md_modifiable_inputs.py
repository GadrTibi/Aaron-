from app.services.revenue import RevenueInputs, compute_revenue, round_to_50_down


def test_md_modifiable_days_and_occ():
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=126,
            taux_occupation_pct=83.0,
            platform_fee_pct=15.0,
            mfy_commission_pct=15.0,
        ),
        days_per_month=26,
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


def test_md_changes_when_days_change():
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=126,
            taux_occupation_pct=83.0,
            platform_fee_pct=15.0,
            mfy_commission_pct=15.0,
        ),
        days_per_month=20,
        estimation_type="MD",
    )

    prix_cible = round_to_50_down(calc["base_estimation"] * 1.00)

    assert calc["revenu_brut"] == 2520
    assert prix_cible == 1800


def test_md_taux_occ_is_display_only():
    base_inputs = dict(
        prix_nuitee=126,
        platform_fee_pct=15.0,
        mfy_commission_pct=15.0,
    )

    calc_low = compute_revenue(
        RevenueInputs(taux_occupation_pct=10.0, **base_inputs),
        days_per_month=26,
        estimation_type="MD",
    )
    calc_high = compute_revenue(
        RevenueInputs(taux_occupation_pct=95.0, **base_inputs),
        days_per_month=26,
        estimation_type="MD",
    )

    assert calc_low["revenu_brut"] == calc_high["revenu_brut"]
