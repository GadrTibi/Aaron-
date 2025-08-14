
import os
import sys

# Ensure the repository root (containing the ``app`` package) is on
# ``sys.path`` **before** importing internal modules. When the script is
# executed directly (``python app/main.py``), only the ``app`` directory is
# added to ``sys.path`` by Python.  Importing using ``from app...`` then fails
# because the parent directory isn't visible.  Adding the base directory here
# makes the package importable in both direct execution and ``python -m``
# contexts.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import streamlit as st

from app.views import estimation, mandat, book

APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- Default directories ----
DEFAULT_TPL_DIR = os.path.join(APP_ROOT, "templates")
DEFAULT_EST_TPL_DIR = os.path.join(DEFAULT_TPL_DIR, "estimation")
DEFAULT_BOOK_TPL_DIR = os.path.join(DEFAULT_TPL_DIR, "book")
DEFAULT_MAND_TPL_DIR = os.path.join(DEFAULT_TPL_DIR, "mandat")
DEFAULT_OUT_DIR = os.path.abspath(os.path.join(APP_ROOT, "..", "output"))
DEFAULT_IMG_CACHE = os.path.join(DEFAULT_OUT_DIR, "_images_cache")

# ---- Build configuration from environment with fallback to defaults ----
CONFIG = {
    "TPL_DIR": os.getenv("MFY_TPL_DIR", DEFAULT_TPL_DIR),
    "EST_TPL_DIR": os.getenv("MFY_EST_TPL_DIR", DEFAULT_EST_TPL_DIR),
    "BOOK_TPL_DIR": os.getenv("MFY_BOOK_TPL_DIR", DEFAULT_BOOK_TPL_DIR),
    "MANDAT_TPL_DIR": os.getenv("MFY_MAND_TPL_DIR", DEFAULT_MAND_TPL_DIR),
    "OUT_DIR": os.getenv("MFY_OUT_DIR", DEFAULT_OUT_DIR),
    "IMG_CACHE_DIR": os.getenv("MFY_IMG_CACHE_DIR", DEFAULT_IMG_CACHE),
}

# ---- Ensure directories exist ----
for k in ("TPL_DIR", "EST_TPL_DIR", "BOOK_TPL_DIR", "MANDAT_TPL_DIR", "OUT_DIR", "IMG_CACHE_DIR"):
    os.makedirs(CONFIG[k], exist_ok=True)

# ---------------- App UI -----------------
st.set_page_config(page_title="MFY - Estimation & Mandat (local)", layout="wide")
st.title("MFY - Outil local (Estimation • Mandat • Book)")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Aller à :", ["Estimation", "Mandat", "Book"])
    st.caption("Chaque page n'affiche que les champs nécessaires au document.")

# -------- Common data (Owner & Property) shown on all pages, compact --------
with st.expander("Données générales (Propriétaire & Bien)", expanded=True):
    col1, col2 = st.columns([1,1])
    with col1:
        proprietaire_nom = st.text_input("Nom (propriétaire)", "", key="own_nom")
        proprietaire_prenom = st.text_input("Prénom (propriétaire)", "", key="own_prenom")
        proprietaire_forme = st.text_input("Forme (M./Mme/SARL...)", "M./Mme", key="own_forme")
    with col2:
        proprietaire_adresse = st.text_input("Adresse (propriétaire)", "", key="own_addr")
        proprietaire_cp = st.text_input("Code postal (propriétaire)", "", key="own_cp")
        proprietaire_ville = st.text_input("Ville (propriétaire)", "", key="own_ville")
    proprietaire_email = st.text_input("Email (propriétaire)", "", key="own_email")

    st.markdown("---")
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        adresse_bien = st.text_input("Adresse du bien", "", key="bien_addr")
        nb_surface = st.number_input("Surface (m², nombre uniquement)", min_value=0.0, value=45.0, step=1.0, key="bien_surface")
    with c2:
        nb_pieces = st.number_input("Nombre de pièces (nombre)", min_value=0, value=2, step=1, key="bien_pieces")
        nb_sdb = st.number_input("Nombre de SDB (nombre)", min_value=0, value=1, step=1, key="bien_sdb")
    with c3:
        nb_couchages = st.number_input("Nombre de couchages (nombre)", min_value=0, value=2, step=1, key="bien_couchages")
        mode_chauffage = st.text_input("Mode de chauffage", "Collectif gaz", key="bien_chauffage")

if page == "Estimation":
    estimation.render(CONFIG)
elif page == "Mandat":
    mandat.render(CONFIG)
elif page == "Book":
    book.render(CONFIG)

