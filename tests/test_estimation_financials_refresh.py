import pytest

from app.views.estimation import _update_financials_state


def test_financials_refresh_updates_state() -> None:
    state: dict[str, float | str] = {}
    _update_financials_state(
        state,
        prix_nuitee=100.0,
        taux_occupation=50.0,
        platform_fee_pct=10.0,
        mfy_commission_pct=20.0,
        cleaning_fee_eur=30.0,
        days_per_month=30.0,
        coef_pess=0.9,
        coef_cible=1.0,
        coef_opt=1.1,
    )

    assert state["revenu_brut"] > 0
    assert state["revenu_net"] >= 0
    assert state["prix_pess"] == 90.0
    assert state["prix_cible"] == 100.0
    assert state["prix_opt"] == pytest.approx(110.0)
    assert state["financials_last_updated"]
