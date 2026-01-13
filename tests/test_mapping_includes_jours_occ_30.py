from app.services.occupancy_utils import build_jours_occ_30_mapping


def test_mapping_includes_jours_occ_30():
    mapping = build_jours_occ_30_mapping(70)
    assert "[[JOURS_OCC_30]]" in mapping
    assert mapping["[[JOURS_OCC_30]]"]
