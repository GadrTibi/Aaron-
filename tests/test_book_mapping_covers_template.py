"""Le VRAI mapping du Book (build_book_mapping) doit couvrir tous les tokens du
template Book versionné, sinon un book généré avec de vraies données garderait
des tokens en clair. Complète test_real_templates_full_substitution (qui teste le
remplacement, ici on teste la COUVERTURE du mapping métier)."""

import glob
import os

import pytest
from pptx import Presentation

from app.services.book_tokens import build_book_mapping
from app.services.pptx_fill import generate_book_pptx
from app.services.token_utils import extract_pptx_tokens_from_presentation

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK_TEMPLATES = glob.glob(os.path.join(REPO, "templates/book/*.pptx"))


@pytest.mark.parametrize("tpl", BOOK_TEMPLATES)
def test_build_book_mapping_covers_all_template_tokens(tpl):
    template_tokens = extract_pptx_tokens_from_presentation(Presentation(tpl))
    ss = {
        "bien_addr": "22 avenue de l'Opéra, 75001 Paris",
        "transport_metro_texte": "Métro, ligne 7, 14",
        "transport_bus_texte": "Bus, ligne 21, 27",
        "q_tx": "Station de taxi place de l'Opéra",
        "bk_porte_entree_texte": "Code portail 1234A",
        "bk_entree_texte": "Hall à droite, ascenseur",
        "bk_appartement_texte": "3e étage, porte gauche",
        "bk_network_name": "MFY-Guest",
        "bk_network_password": "Bienvenue2026",
    }
    mapping = build_book_mapping(ss)
    uncovered = {t for t in template_tokens if t not in mapping}
    assert not uncovered, f"Tokens du template non couverts par build_book_mapping : {uncovered}"


@pytest.mark.parametrize("tpl", BOOK_TEMPLATES)
def test_book_generation_with_real_mapping_leaves_no_token(tpl, tmp_path):
    ss = {
        "bien_addr": "22 avenue de l'Opéra, 75001 Paris",
        "transport_metro_texte": "Métro, ligne 7, 14",
        "transport_bus_texte": "Bus, ligne 21, 27",
        "q_tx": "Station de taxi place de l'Opéra",
        "bk_porte_entree_texte": "Code portail 1234A",
        "bk_entree_texte": "Hall à droite, ascenseur",
        "bk_appartement_texte": "3e étage, porte gauche",
        "bk_network_name": "MFY-Guest",
        "bk_network_password": "Bienvenue2026",
    }
    out = str(tmp_path / os.path.basename(tpl))
    generate_book_pptx(tpl, out, build_book_mapping(ss))
    assert extract_pptx_tokens_from_presentation(Presentation(out)) == set()
