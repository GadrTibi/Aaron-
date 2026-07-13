from app.services.revenue import RevenueInputs, compute_revenue, round_to_50_down


def test_md_matches_client_numbers():
    # Reproduit l'appel réel de l'app pour un MD : les JOURS/mois pilotent le
    # revenu (le taux d'occupation est affiché mais ne re-multiplie pas). Cf.
    # docs/refonte/00-CDC-REFERENCE.md §3.2 et point ouvert P2.
    # Le test précédent omettait days_per_month=26 et retombait sur le défaut 30
    # (=> 3780 au lieu de 3276) : c'était un bug du TEST, pas du calcul.
    calc = compute_revenue(
        RevenueInputs(
            prix_nuitee=126,
            taux_occupation_pct=83.0,  # affiché seulement, ne multiplie pas
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

    # 126 x 26 = 3276 ; frais plateforme = round(3276*0.15) = round(491.4) = 491.
    # NB (point ouvert P3) : le doc de transmission RAPPORTE 492 / 910. Le code fige
    # 491 / 909 (round(), cohérent avec le jeu de référence CD) ; 492 est inatteignable
    # par la même règle d'arrondi que celle qui reproduit le CD. Divergence NON tranchée,
    # à confirmer avec le screenshot client réel — on ne préjuge pas que 492 est faux.
    assert calc["revenu_brut"] == 3276
    assert calc["platform_fee_eur"] == 491
    assert calc["mfy_commission_eur"] == 418
    assert calc["frais_generaux"] == 909
    assert prix_pess == 2200
    assert prix_cible == 2350
    assert prix_opt == 2500
