"""Le motif de détection des tokens DOCX code l'INTENTION (placeholder de fusion vs
terme juridique du corps), pas une forme figée. Garantit qu'un vrai token n'est
jamais rendu invisible au garde-fou « document incomplet » (cf. token_utils)."""

import pytest

from app.services.token_utils import DOCX_TOKEN_PATTERN

VRAIS_TOKENS = [
    "«Nom_du_propriétaire»",
    "«MANDAT_JOUR_SIGNATURE»",
    "«M__de_rémunération_MFY»",
    "«Adresse_du_bien_loué»",
    "«Nombre_de_pièces_deau»",
]

TERMES_JURIDIQUES = [
    "« Mandant »",
    "« Bien »",
    "« Mandataire »",
    "«\xa0Notice d'Information sur la Protection des Consommateurs\xa0»",
]


@pytest.mark.parametrize("tok", VRAIS_TOKENS)
def test_detecte_les_vrais_tokens(tok):
    assert DOCX_TOKEN_PATTERN.findall(tok) == [tok]


@pytest.mark.parametrize("terme", TERMES_JURIDIQUES)
def test_exclut_les_termes_juridiques(terme):
    assert DOCX_TOKEN_PATTERN.findall(terme) == []


def test_detecte_un_placeholder_a_espaces_internes():
    # Point clé de la correction : un token à espaces internes (mais pas collés aux
    # guillemets) doit rester DÉTECTÉ — «\w+» le rendait invisible (faux négatif).
    assert DOCX_TOKEN_PATTERN.findall("«Nom du gérant»") == ["«Nom du gérant»"]


def test_token_d_un_seul_caractere():
    assert DOCX_TOKEN_PATTERN.findall("«X»") == ["«X»"]
