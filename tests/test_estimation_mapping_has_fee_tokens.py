from app.services.revenue import RevenueInputs, build_revenue_token_mapping, compute_revenue


def test_estimation_mapping_has_fee_tokens():
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=150,
            taux_occupation_pct=60,
            platform_fee_pct=15,
            mfy_commission_pct=20,
            frais_menage_mensuels=35,
        )
    )

    mapping = build_revenue_token_mapping(calc)

    expected_tokens = [
        "[[PLATFORM_FEE_PCT]]",
        "[[PLATFORM_FEE_EUR]]",
        "[[CLEANING_FEE_EUR]]",
        "[[MFY_COMMISSION_PCT]]",
        "[[MFY_COMMISSION_EUR]]",
    ]
    for token in expected_tokens:
        assert token in mapping
        assert mapping[token]
