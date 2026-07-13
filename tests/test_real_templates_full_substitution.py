"""Test du MOTEUR de substitution sur les VRAIS templates versionnés.

Portée exacte :
- Estimation / Book (mapping auto-référentiel `{token: "X"}`) : vérifie que le moteur
  remplace TOUT token présent dans le template — c'est un test du moteur, PAS de la
  complétude du mapping réel de l'app.
- Mandat (vrai `build_mandat_mapping`) : teste en plus la complétude du mapping métier.

La complétude du mapping RÉEL côté Book est couverte par
`test_book_mapping_covers_template.py` ; côté Estimation, par les `test_estimation_mapping_*`.
"""

import glob
import os

import pytest
from pptx import Presentation

from app.services.mandat_tokens import build_mandat_mapping
from app.services.docx_fill import generate_docx_from_template
from app.services.pptx_fill import generate_estimation_pptx, generate_book_pptx
from app.services.token_utils import (
    extract_docx_tokens,
    extract_pptx_tokens_from_presentation,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pptx_tokens(path):
    return set(extract_pptx_tokens_from_presentation(Presentation(path)))


@pytest.mark.parametrize("tpl", glob.glob(os.path.join(REPO, "templates/estimation/**/*.pptx"), recursive=True))
def test_estimation_templates_fully_substituted(tpl, tmp_path):
    tokens = _pptx_tokens(tpl)
    assert tokens, f"Aucun token détecté dans {tpl} (template suspect)"
    out = str(tmp_path / os.path.basename(tpl))
    generate_estimation_pptx(tpl, out, {t: "X" for t in tokens})
    assert _pptx_tokens(out) == set(), "Des tokens [[...]] restent dans l'estimation générée"


@pytest.mark.parametrize("tpl", glob.glob(os.path.join(REPO, "templates/book/*.pptx")))
def test_book_templates_fully_substituted(tpl, tmp_path):
    tokens = _pptx_tokens(tpl)
    assert tokens, f"Aucun token détecté dans {tpl} (template suspect)"
    out = str(tmp_path / os.path.basename(tpl))
    generate_book_pptx(tpl, out, {t: "X" for t in tokens})
    assert _pptx_tokens(out) == set(), "Des tokens [[...]] restent dans le book généré"


@pytest.mark.parametrize("tpl", glob.glob(os.path.join(REPO, "templates/mandat/**/*.docx"), recursive=True))
def test_mandat_templates_fully_substituted(tpl, tmp_path):
    ss = {
        "owner_type": "Personne physique", "own_nom": "Dupont", "own_prenom": "Jean",
        "own_addr": "1 rue de Rivoli", "own_cp": "75001", "own_ville": "Paris",
        "own_email": "jean@ex.fr", "bien_addr": "22 av de l'Opera", "bien_surface": 45,
        "bien_pieces": 2, "bien_sdb": 1, "bien_couchages": 2, "bien_chauffage": "Collectif gaz",
        "bien_eau_chaude": "Individuel", "mandat_destination_bien": "Location meublée",
        "mandat_commission_pct": 15, "mandat_date_debut": "01/01/2026",
        "mandat_remise_pieces": "2 jeux de clés", "mandat_type_pieces_eau": "Salle de bain",
    }
    mapping = build_mandat_mapping(ss)
    out = str(tmp_path / os.path.basename(tpl))
    generate_docx_from_template(tpl, out, mapping)
    # Après correction du pattern, seuls les VRAIS tokens «\w+» sont détectés :
    # les termes juridiques « Mandant » / « Bien » ne sont pas des tokens.
    assert extract_docx_tokens(out) == set(), "Des tokens «...» restent dans le mandat généré"
