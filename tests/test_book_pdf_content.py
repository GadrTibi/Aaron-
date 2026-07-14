"""Le PDF d'accueil (bouton « PDF simplifié ») doit contenir les VRAIES données de
session, pas un document blanc. Ferme l'angle mort : auparavant book.py appelait
build_book_pdf avec des chaînes vides -> PDF blanc + message « OK » trompeur."""

import os

from app.services.book_tokens import build_book_mapping, build_book_pdf_sections
from app.services.book_pdf import build_book_pdf

SS = {
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


def test_pdf_sections_contain_real_data():
    titre, intro, sections = build_book_pdf_sections(build_book_mapping(SS))
    assert "Opéra" in titre
    assert sections, "sections vides alors que la session est renseignée (PDF serait blanc)"
    titres = {t for t, _ in sections}
    assert {"Adresse", "Transports", "Accès au logement", "Wi-Fi"} <= titres
    joined = "\n".join(c for _, c in sections)
    assert "Métro" in joined and "MFY-Guest" in joined and "1234A" in joined


def test_pdf_sections_empty_when_no_data():
    # Mapping vide -> aucune section -> book.py affiche un warning au lieu d'un PDF blanc.
    _, _, sections = build_book_pdf_sections(build_book_mapping({}))
    assert sections == []


def test_pdf_file_generated_non_trivial(tmp_path):
    titre, intro, sections = build_book_pdf_sections(build_book_mapping(SS))
    out = str(tmp_path / "book.pdf")
    build_book_pdf(out, titre, intro, sections)
    assert os.path.exists(out)
    # Un PDF avec du contenu réel pèse nettement plus qu'un canevas vide (~ <1 Ko).
    assert os.path.getsize(out) > 1200
