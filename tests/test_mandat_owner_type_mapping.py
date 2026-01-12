import pytest

from app.services.mandat_tokens import build_mandat_mapping


def test_mandat_mapping_personne_physique():
    mapping = build_mandat_mapping(
        {
            "owner_type": "Personne physique",
            "owner_last_name": "Durand",
            "owner_first_name": "Alice",
            "owner_address": "1 rue de la Paix",
        }
    )

    assert mapping["«Nom_du_propriétaire»"] == "Durand"
    assert mapping["«Prénom_du_propriétaire»"] == "Alice"
    assert mapping["«Adresse_du_propriétaire»"] == "1 rue de la Paix"
    assert mapping["«Forme_du_propriétaire»"] == "Personne physique"


def test_mandat_mapping_personne_morale():
    mapping = build_mandat_mapping(
        {
            "owner_type": "Personne morale",
            "company_legal_form": "SAS",
            "company_name": "ACME",
            "company_address": "10 avenue Victor Hugo",
        }
    )

    assert "Personne morale" in mapping["«Forme_du_propriétaire»"]
    assert mapping["«Nom_du_propriétaire»"] == "ACME"
    assert mapping["«Prénom_du_propriétaire»"] == ""
    assert mapping["«Adresse_du_propriétaire»"] == "10 avenue Victor Hugo"


def test_mandat_mapping_requires_owner_type():
    with pytest.raises(ValueError, match="Type de propriétaire manquant"):
        build_mandat_mapping({})
