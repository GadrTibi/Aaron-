from app.services.occupancy_utils import build_jours_occ_30_mapping
from app.services.revenue import ESTIMATION_DAYS_PER_MONTH_MD


def test_cd_jours_occ_30_uses_taux_occ_for_phrase():
    mapping = build_jours_occ_30_mapping(50.0, include_unit=False)

    assert mapping["[[JOURS_OCC_30]]"] == "15"


def test_md_jours_occ_30_is_fixed_days_per_month():
    mapping = build_jours_occ_30_mapping(80.0, days_value=ESTIMATION_DAYS_PER_MONTH_MD, include_unit=False)

    assert mapping["[[JOURS_OCC_30]]"] == "26"
