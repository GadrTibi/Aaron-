
import os, sys, re, tempfile
from datetime import datetime

import streamlit as st
import requests

# Ensure package path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.services.revenue import RevenueInputs, compute_revenue
from app.services.pptx_fill import generate_estimation_pptx
from app.services.docx_fill import replace_placeholders_docx
from app.services.poi import fetch_pois, fetch_transports, suggest_places
from app.services.book_pdf import build_book_pdf
from app.services.geocode import geocode_address
from app.services.image_search import find_place_image_urls

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(APP_ROOT, "templates")
OUT_DIR = os.path.abspath(os.path.join(APP_ROOT, "..", "output"))
os.makedirs(OUT_DIR, exist_ok=True)

# ---- Multi-template directories ----
EST_TPL_DIR = os.path.join(TPL_DIR, "estimation")
MAN_TPL_DIR = os.path.join(TPL_DIR, "mandat")
BOOK_TPL_DIR = os.path.join(TPL_DIR, "book")
for _d in (EST_TPL_DIR, MAN_TPL_DIR, BOOK_TPL_DIR):
    os.makedirs(_d, exist_ok=True)

def _sanitize_filename(name: str, ext: str) -> str:
    base = os.path.basename(name)
    safe = re.sub(r"[^A-Za-z0-9 _\-.]", "_", base)
    if not safe.lower().endswith(f".{ext}"):
        safe += f".{ext}"
    return safe

@st.cache_data(ttl=5)
def list_templates(dirpath: str, ext: str):
    try:
        files = [f for f in os.listdir(dirpath) if f.lower().endswith(f".{ext}")]
        files.sort()
        return files
    except Exception:
        return []

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

# =====================================================
# =============== ESTIMATION PAGE =====================
# =====================================================
if page == "Estimation":
    # ---------- APPLY PENDING PREFILL BEFORE WIDGETS ----------
    if "__prefill" in st.session_state and isinstance(st.session_state["__prefill"], dict):
        # apply and pop so we don't loop
        for k, v in st.session_state["__prefill"].items():
            st.session_state[k] = v
        st.session_state.pop("__prefill", None)

    # ---- Templates Estimation (PPTX) ----
    st.subheader("Templates Estimation (PPTX)")
    st.caption(f"Dossier : {EST_TPL_DIR}")
    est_list = list_templates(EST_TPL_DIR, "pptx")
    uploaded_tpls = st.file_uploader("Ajouter des templates PPTX", type=["pptx"], accept_multiple_files=True, key="up_est")
    if uploaded_tpls:
        saved = 0
        for up in uploaded_tpls:
            safe_name = _sanitize_filename(up.name, "pptx")
            dst = os.path.join(EST_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name); i = 2
                while os.path.exists(os.path.join(EST_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(EST_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        est_list = list_templates(EST_TPL_DIR, "pptx")
    legacy_est = os.path.join(TPL_DIR, "estimation_template.pptx")
    has_legacy_est = os.path.exists(legacy_est)
    options = (["estimation_template.pptx (héritage)"] if has_legacy_est else []) + est_list
    chosen_est = st.selectbox("Choisir le template Estimation", options=options if options else ["(aucun)"])
    def resolve_est_path(label: str):
        if not label or label == "(aucun)":
            return None
        if label == "estimation_template.pptx (héritage)":
            return legacy_est
        return os.path.join(EST_TPL_DIR, label)

    # ---- Quartier & transports (Slide 4) ----
    st.subheader("Quartier (Slide 4)")
    quartier_texte = st.text_area("Texte d'intro du quartier (paragraphe)", st.session_state.get("q_txt", "Texte libre saisi par l'utilisateur."), key="q_txt")
    colQ1, colQ2, colQ3 = st.columns(3)
    with colQ1:
        transport_taxi = st.text_input("Transport - Taxi", st.session_state.get("q_tx", "Station de taxi (…)"), key="q_tx")
    with colQ2:
        transport_metro = st.text_input("Transport - Métro", st.session_state.get("q_metro", "Métro …"), key="q_metro")
    with colQ3:
        transport_bus = st.text_input("Transport - Bus", st.session_state.get("q_bus", "Bus …"), key="q_bus")

    # ---- Incontournables (3), Spots (2), Visites (2 + images) ----
    st.subheader("Adresses du quartier (Slide 4)")
    colI1, colI2, colI3 = st.columns(3)
    with colI1:
        incontournable_1 = st.text_input("Incontournable 1 (nom)", st.session_state.get("i1", ""), key="i1")
    with colI2:
        incontournable_2 = st.text_input("Incontournable 2 (nom)", st.session_state.get("i2", ""), key="i2")
    with colI3:
        incontournable_3 = st.text_input("Incontournable 3 (nom)", st.session_state.get("i3", ""), key="i3")

    colS1, colS2 = st.columns(2)
    with colS1:
        spot_1 = st.text_input("Spot à faire 1 (nom)", st.session_state.get("s1", ""), key="s1")
    with colS2:
        spot_2 = st.text_input("Spot à faire 2 (nom)", st.session_state.get("s2", ""), key="s2")

    st.markdown("**Lieux à visiter (2) — images auto (Wikipedia/Commons)**")
    colV1, colV2 = st.columns(2)
    with colV1:
        visite_1 = st.text_input("Lieu à visiter 1 (nom)", st.session_state.get("v1", ""), key="v1")
    with colV2:
        visite_2 = st.text_input("Lieu à visiter 2 (nom)", st.session_state.get("v2", ""), key="v2")

    if "visite1_imgs" not in st.session_state: st.session_state.visite1_imgs = []
    if "visite2_imgs" not in st.session_state: st.session_state.visite2_imgs = []
    if "visite1_choice" not in st.session_state: st.session_state.visite1_choice = None
    if "visite2_choice" not in st.session_state: st.session_state.visite2_choice = None

    cimg1, cimg2 = st.columns(2)
    with cimg1:
        if st.button("Chercher images pour Visite 1"):
            st.session_state.visite1_imgs = find_place_image_urls(st.session_state.get("v1","") or "", lang="fr", limit=6)
        if st.session_state.visite1_imgs:
            st.write("Choisir une image pour Visite 1 :")
            for idx, url in enumerate(st.session_state.visite1_imgs):
                st.image(url, caption=f"Option {idx+1}", use_column_width=True)
            st.session_state.visite1_choice = st.number_input("Choix image Visite 1 (numéro)", min_value=1, max_value=len(st.session_state.visite1_imgs), value=1, step=1, key="v1_choice")
    with cimg2:
        if st.button("Chercher images pour Visite 2"):
            st.session_state.visite2_imgs = find_place_image_urls(st.session_state.get("v2","") or "", lang="fr", limit=6)
        if st.session_state.visite2_imgs:
            st.write("Choisir une image pour Visite 2 :")
            for idx, url in enumerate(st.session_state.visite2_imgs):
                st.image(url, caption=f"Option {idx+1}", use_column_width=True)
            st.session_state.visite2_choice = st.number_input("Choix image Visite 2 (numéro)", min_value=1, max_value=len(st.session_state.visite2_imgs), value=1, step=1, key="v2_choice")

    # Points forts & Challenges (Slide 5)
    st.subheader("Points forts & Challenges (Slide 5)")
    colPF, colCH = st.columns(2)
    with colPF:
        point_fort_1 = st.text_input("Point fort 1", st.session_state.get("pf1", "Proche des transports"), key="pf1")
        point_fort_2 = st.text_input("Point fort 2", st.session_state.get("pf2", "Récemment rénové"), key="pf2")
    with colCH:
        challenge_1 = st.text_input("Challenge 1", st.session_state.get("ch1", "Pas d’ascenseur"), key="ch1")
        challenge_2 = st.text_input("Challenge 2", st.session_state.get("ch2", "Bruit de la rue en journée"), key="ch2")

    # ---- POI via adresse ----
    st.subheader("Points d'intérêt (POI)")
    addr_for_geo = st.text_input("Adresse pour géocoder (texte ou lat,lon)", value=st.session_state.get("poi_addr", st.session_state.get("bien_addr","")), key="poi_addr")
    radius_m = st.slider("Rayon POI (m)", min_value=300, max_value=3000, value=st.session_state.get("poi_r", 1200), step=100, key="poi_r")
    auto_after_geocode = st.toggle("Remplir automatiquement Transports + Suggestions après géocodage", value=st.session_state.get("auto_after_geocode", True), key="auto_after_geocode", help="Si activé, dès que l'adresse est géocodée on remplit les champs pertinents.")

    lat, lon = None, None
    LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
    m = LATLON_RE.match(addr_for_geo or "")
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        st.session_state['geo_lat'] = lat; st.session_state['geo_lon'] = lon
    else:
        if st.button("Géocoder l'adresse"):
            with st.spinner("Recherche d'adresse…"):
                glat, glon = geocode_address(addr_for_geo)
            if glat is None:
                st.error("Adresse introuvable. Vérifie l'orthographe ou ajoute la ville/pays.")
            else:
                st.session_state['geo_lat'] = glat
                st.session_state['geo_lon'] = glon
                lat, lon = glat, glon
                st.success(f"Adresse localisée: {lat:.6f}, {lon:.6f}")
                if st.session_state.get("auto_after_geocode", True):
                    prefill = {}
                    try:
                        tr = fetch_transports(lat, lon, radius_m=radius_m)
                        if tr.get('taxi'): prefill['q_tx'] = tr['taxi']
                        if tr.get('metro'): prefill['q_metro'] = tr['metro']
                        if tr.get('bus'): prefill['q_bus'] = tr['bus']
                    except Exception as e:
                        st.info(f"Transports non chargés: {e}")
                    try:
                        sug = suggest_places(lat, lon, radius_m=radius_m)
                        inc = sug.get('incontournables', [])
                        sp = sug.get('spots', [])
                        vs = sug.get('visites', [])
                        if len(inc) > 0: prefill['i1'] = inc[0]
                        if len(inc) > 1: prefill['i2'] = inc[1]
                        if len(inc) > 2: prefill['i3'] = inc[2]
                        if len(sp) > 0: prefill['s1'] = sp[0]
                        if len(sp) > 1: prefill['s2'] = sp[1]
                        if len(vs) > 0: prefill['v1'] = vs[0]
                        if len(vs) > 1: prefill['v2'] = vs[1]
                    except Exception as e:
                        st.info(f"Suggestions non chargées: {e}")
                    if prefill:
                        st.session_state["__prefill"] = prefill
                        st.rerun()

    if 'geo_lat' in st.session_state and 'geo_lon' in st.session_state and (lat is None or lon is None):
        lat = st.session_state['geo_lat']; lon = st.session_state['geo_lon']

    if "pois" not in st.session_state: st.session_state["pois"] = []
    if st.button("Chercher les POI (OSM)"):
        if lat is None or lon is None:
            st.warning("Géocode d'abord l'adresse ou saisis lat,lon.")
        else:
            try:
                st.session_state["pois"] = fetch_pois(lat, lon, radius_m=radius_m)
            except Exception as e:
                st.warning(f"POI: {e}")

    selected_poi_names = []
    pois = st.session_state.get("pois", [])
    if pois:
        st.write("Sélectionnez jusqu'à 3 POI pertinents :")
        poi_names = [f"{p['name']} ({p['category']})" for p in pois]
        picked = st.multiselect("POI", poi_names, default=poi_names[:3] if poi_names else [])
        selected_poi_names = picked[:3]

    st.markdown('---')
    colAuto1, colAuto2 = st.columns(2)
    with colAuto1:
        if st.button('Auto-remplir Transports depuis l\'adresse'):
            if ('geo_lat' in st.session_state) and ('geo_lon' in st.session_state):
                try:
                    tr = fetch_transports(st.session_state['geo_lat'], st.session_state['geo_lon'], radius_m=radius_m)
                    prefill = {}
                    if tr.get('taxi'): prefill['q_tx'] = tr['taxi']
                    if tr.get('metro'): prefill['q_metro'] = tr['metro']
                    if tr.get('bus'): prefill['q_bus'] = tr['bus']
                    if prefill:
                        st.session_state["__prefill"] = prefill
                        st.rerun()
                except Exception as e:
                    st.info(f"Transports non chargés: {e}")
            else:
                st.warning('Géocode d\'abord l\'adresse.')
    with colAuto2:
        if st.button('Suggérer Incontournables/Spots/Visites'):
            if ('geo_lat' in st.session_state) and ('geo_lon' in st.session_state):
                try:
                    sug = suggest_places(st.session_state['geo_lat'], st.session_state['geo_lon'], radius_m=radius_m)
                    inc = sug.get('incontournables', [])
                    sp = sug.get('spots', [])
                    vs = sug.get('visites', [])
                    prefill = {}
                    if len(inc) > 0: prefill['i1'] = inc[0]
                    if len(inc) > 1: prefill['i2'] = inc[1]
                    if len(inc) > 2: prefill['i3'] = inc[2]
                    if len(sp) > 0: prefill['s1'] = sp[0]
                    if len(sp) > 1: prefill['s2'] = sp[1]
                    if len(vs) > 0: prefill['v1'] = vs[0]
                    if len(vs) > 1: prefill['v2'] = vs[1]
                    if prefill:
                        st.session_state["__prefill"] = prefill
                        st.rerun()
                except Exception as e:
                    st.info(f"Suggestions non chargées: {e}")
            else:
                st.warning('Géocode d\'abord l\'adresse.')

    # ---- Revenus + scénarios ----
    st.subheader("Paramètres revenus")
    colA, colB, colC, colD = st.columns(4)
    with colA:
        prix_nuitee = st.number_input("Prix par nuitée (€)", min_value=0.0, value=120.0, step=5.0, key="rn_prix")
    with colB:
        taux_occupation = st.slider("Taux d'occupation (%)", min_value=0, max_value=100, value=70, step=1, key="rn_occ")
    with colC:
        commission_mfy = st.slider("Commission MFY (%)", min_value=0, max_value=50, value=20, step=1, key="rn_comm")
    with colD:
        frais_menage = st.number_input("Frais de ménage (mensuels, €)", min_value=0.0, value=0.0, step=5.0, key="rn_menage")

    st.markdown("**Scénarios de prix (nuitée)**")
    c1, c2, c3 = st.columns(3)
    with c1:
        coef_pess = st.number_input("Coef pessimiste", min_value=0.5, max_value=2.0, value=0.90, step=0.05, key="sc_p")
    with c2:
        coef_cible = st.number_input("Coef cible", min_value=0.5, max_value=2.0, value=1.00, step=0.05, key="sc_c")
    with c3:
        coef_opt = st.number_input("Coef optimiste", min_value=0.5, max_value=2.0, value=1.10, step=0.05, key="sc_o")

    calc = compute_revenue(RevenueInputs(
        prix_nuitee=float(prix_nuitee),
        taux_occupation_pct=float(taux_occupation),
        commission_pct=float(commission_mfy),
        frais_menage_mensuels=float(frais_menage),
    ))

    REV_BRUT = calc["revenu_brut"]
    FRAIS_GEN = calc["frais_generaux"]
    REV_NET  = calc["revenu_net"]
    JOURS_OCC = calc["jours_occupes"]

    st.metric("Jours loués / mois", f"{JOURS_OCC:.1f} j")
    colX, colY, colZ = st.columns(3)
    colX.metric("Revenu brut", f"{REV_BRUT:.0f} €")
    colY.metric("Frais généraux", f"{FRAIS_GEN:.0f} €")
    colZ.metric("Revenu net", f"{REV_NET:.0f} €")

    # Graphe
    try:
        import matplotlib.pyplot as plt
        fig = plt.figure()
        plt.bar(["Brut","Frais","Net"], [REV_BRUT, FRAIS_GEN, REV_NET])
        st.pyplot(fig)
        chart_path = os.path.join(OUT_DIR, "revenus_chart.png")
        fig.savefig(chart_path, bbox_inches="tight")
    except Exception:
        chart_path = None
        st.info("Chart non généré (matplotlib manquant)")

    # Scénarios prix
    PRIX_PESS = prix_nuitee * coef_pess
    PRIX_CIBLE = prix_nuitee * coef_cible
    PRIX_OPT = prix_nuitee * coef_opt

    # Mapping Estimation
    mapping = {
        # Slide 4
        "[[ADRESSE]]": st.session_state.get("bien_addr",""),
        "[[QUARTIER_TEXTE]]": st.session_state.get("q_txt",""),
        "[[TRANSPORT_TAXI_TEXTE]]": st.session_state.get('q_tx', ''),
        "[[TRANSPORT_METRO_TEXTE]]": st.session_state.get('q_metro', ''),
        "[[TRANSPORT_BUS_TEXTE]]": st.session_state.get('q_bus', ''),
        "[[INCONTOURNABLE_1_NOM]]": st.session_state.get('i1', ''),
        "[[INCONTOURNABLE_2_NOM]]": st.session_state.get('i2', ''),
        "[[INCONTOURNABLE_3_NOM]]": st.session_state.get('i3', ''),
        "[[SPOT_1_NOM]]": st.session_state.get('s1', ''),
        "[[SPOT_2_NOM]]": st.session_state.get('s2', ''),
        "[[VISITE_1_NOM]]": st.session_state.get('v1', ''),
        "[[VISITE_2_NOM]]": st.session_state.get('v2', ''),
        # Slide 5 (valeurs numériques + PF/Challenges)
        "[[NB_SURFACE]]": f"{st.session_state.get('bien_surface',0):.0f}",
        "[[NB_PIECES]]": f"{int(st.session_state.get('bien_pieces',0))}",
        "[[NB_SDB]]": f"{int(st.session_state.get('bien_sdb',0))}",
        "[[NB_COUCHAGES]]": f"{int(st.session_state.get('bien_couchages',0))}",
        "[[MODE_CHAUFFAGE]]": st.session_state.get('bien_chauffage',''),
        "[[POINT_FORT_1]]": st.session_state.get('pf1',''),
        "[[POINT_FORT_2]]": st.session_state.get('pf2',''),
        "[[CHALLENGE_1]]": st.session_state.get('ch1',''),
        "[[CHALLENGE_2]]": st.session_state.get('ch2',''),
        # Slide 6
        "[[PRIX_NUIT]]": f"{st.session_state.get('rn_prix',0):.0f} €",
        "[[TAUX_OCC]]": f"{st.session_state.get('rn_occ',0)} %",
        "[[REV_BRUT]]": f"{REV_BRUT:.0f} €",
        "[[FRAIS_GEN]]": f"{FRAIS_GEN:.0f} €",
        "[[REV_NET]]": f"{REV_NET:.0f} €",
        "[[JOURS_OCC]]": f"{JOURS_OCC:.1f} j",
        "[[PRIX_PESSIMISTE]]": f"{PRIX_PESS:.0f} €",
        "[[PRIX_CIBLE]]": f"{PRIX_CIBLE:.0f} €",
        "[[PRIX_OPTIMISTE]]": f"{PRIX_OPT:.0f} €",
    }

    # Images for VISITE_1/2
    image_by_shape = {}
    tmp_files = []
    def _download(url):
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            fd, path = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
            with open(path, "wb") as f:
                f.write(r.content)
            tmp_files.append(path); return path
        except Exception:
            return None

    if st.session_state.get('visite1_imgs') and st.session_state.get('visite1_choice'):
        idx = int(st.session_state['visite1_choice']) - 1
        arr = st.session_state['visite1_imgs']
        if 0 <= idx < len(arr):
            p = _download(arr[idx])
            if p: image_by_shape["VISITE_1_IMG"] = p
    if st.session_state.get('visite2_imgs') and st.session_state.get('visite2_choice'):
        idx = int(st.session_state['visite2_choice']) - 1
        arr = st.session_state['visite2_imgs']
        if 0 <= idx < len(arr):
            p = _download(arr[idx])
            if p: image_by_shape["VISITE_2_IMG"] = p

    # ---- Generate Estimation ----
    st.subheader("Générer l'Estimation (PPTX)")
    est_tpl_path = resolve_est_path(chosen_est)
    if st.button("Générer le PPTX (Estimation)"):
        if not est_tpl_path or not os.path.exists(est_tpl_path):
            st.error("Aucun template PPTX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus.")
            st.stop()
        pptx_out = os.path.join(OUT_DIR, f"Estimation - {st.session_state.get('bien_addr','bien')}.pptx")
        generate_estimation_pptx(est_tpl_path, pptx_out, mapping, chart_image=chart_path, image_by_shape=image_by_shape or None)
        st.success(f"OK: {pptx_out}")
        with open(pptx_out, "rb") as f:
            st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))

# =====================================================
# =============== MANDAT PAGE =========================
# =====================================================
elif page == "Mandat":
    st.subheader("Templates Mandat (DOCX)")
    st.caption(f"Dossier : {MAN_TPL_DIR}")
    man_list = list_templates(MAN_TPL_DIR, "docx")
    uploaded_docx = st.file_uploader("Ajouter des templates DOCX", type=["docx"], accept_multiple_files=True, key="up_man")
    if uploaded_docx:
        saved = 0
        for up in uploaded_docx:
            safe_name = _sanitize_filename(up.name, "docx")
            dst = os.path.join(MAN_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name); i = 2
                while os.path.exists(os.path.join(MAN_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(MAN_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        man_list = list_templates(MAN_TPL_DIR, "docx")
    legacy_man = os.path.join(TPL_DIR, "mandat_template.docx")
    has_legacy_man = os.path.exists(legacy_man)
    options = (["mandat_template.docx (héritage)"] if has_legacy_man else []) + man_list
    chosen_man = st.selectbox("Choisir le template Mandat", options=options if options else ["(aucun)"])
    def resolve_man_path(label: str):
        if not label or label == "(aucun)":
            return None
        if label == "mandat_template.docx (héritage)":
            return legacy_man
        return os.path.join(MAN_TPL_DIR, label)

    st.subheader("Champs spécifiques Mandat")
    date_debut = st.date_input("Date de début de mandat", datetime.today(), key="man_date")
    mode_eau_chaude = st.text_input("Mode de production d'eau chaude", "Ballon électrique", key="man_eau")

    mandat_map = {
        "«Forme_du_propriétaire»": st.session_state.get("own_forme",""),
        "«Nom_du_propriétaire»": st.session_state.get("own_nom",""),
        "«Prénom_du_propriétaire»": st.session_state.get("own_prenom",""),
        "«Adresse_du_propriétaire»": st.session_state.get("own_addr",""),
        "«Code_postal_du_propriétaire»": st.session_state.get("own_cp",""),
        "«Ville_du_propriétaire»": st.session_state.get("own_ville",""),
        "«Adresse_du_bien_loué»": st.session_state.get("bien_addr",""),
        "«Surface_totale_du_bien»": str(int(st.session_state.get("bien_surface",0))),
        "«Nombre_de_pièces_du_bien»": str(int(st.session_state.get("bien_pieces",0))),
        "«Nombre_de_pax»": str(int(st.session_state.get("bien_couchages",0))),
        "«Mode_de_production_de_chauffage»": st.session_state.get("bien_chauffage",""),
        "«Mode_de_production_deau_chaude_sanitair»": mode_eau_chaude,
        "«Mail_du_propriétaire»": st.session_state.get("own_email",""),
        "«Date_de_début_de_mandat»": date_debut.strftime("%d/%m/%Y"),
    }

    st.subheader("Générer le Mandat (DOCX)")
    man_tpl_path = resolve_man_path(chosen_man)
    if st.button("Générer le DOCX (Mandat)"):
        if not man_tpl_path or not os.path.exists(man_tpl_path):
            st.error("Aucun template DOCX sélectionné ou fichier introuvable. Déposez/choisissez un template ci-dessus.")
            st.stop()
        docx_out = os.path.join(OUT_DIR, f"Mandat - {st.session_state.get('own_nom','client')}.docx")
        replace_placeholders_docx(man_tpl_path, docx_out, mandat_map)
        st.success(f"OK: {docx_out}")
        with open(docx_out, "rb") as f:
            st.download_button("Télécharger le DOCX", data=f.read(), file_name=os.path.basename(docx_out))

# =====================================================
# =============== BOOK PAGE ===========================
# =====================================================
elif page == "Book":
    st.subheader("Templates Book (PPTX)")
    st.caption(f"Dossier : {BOOK_TPL_DIR}")
    book_list = list_templates(BOOK_TPL_DIR, "pptx")
    uploaded_book = st.file_uploader("Ajouter des templates PPTX (Book)", type=["pptx"], accept_multiple_files=True, key="up_book")
    if uploaded_book:
        saved = 0
        for up in uploaded_book:
            safe_name = _sanitize_filename(up.name, "pptx")
            dst = os.path.join(BOOK_TPL_DIR, safe_name)
            if os.path.exists(dst):
                base, ext = os.path.splitext(safe_name); i = 2
                while os.path.exists(os.path.join(BOOK_TPL_DIR, f"{base} ({i}){ext}")):
                    i += 1
                dst = os.path.join(BOOK_TPL_DIR, f"{base} ({i}){ext}")
            with open(dst, "wb") as f:
                f.write(up.getbuffer())
            saved += 1
        st.success(f"{saved} template(s) ajouté(s).")
        book_list = list_templates(BOOK_TPL_DIR, "pptx")
    chosen_book = st.selectbox("Choisir le template Book (PPTX)", options=book_list if book_list else ["(aucun)"])
    def resolve_book_path(label: str):
        if not label or label == "(aucun)":
            return None
        return os.path.join(BOOK_TPL_DIR, label)

    st.subheader("Contenu du Book")
    titre = st.text_input("Titre du book", st.session_state.get("bk_titre","Book - Présentation du bien"), key="bk_titre")
    intro_default = f"Adresse: {st.session_state.get('bien_addr','')}\nSurface: {st.session_state.get('bien_surface',0):.0f} m² - Pièces: {st.session_state.get('bien_pieces',0)} - Couchages: {st.session_state.get('bien_couchages',0)}\nPoints forts: (à détailler)\nPoints faibles: (à détailler)\n"
    intro = st.text_area("Intro", st.session_state.get("bk_intro", intro_default), key="bk_intro")

    st.markdown("**Photos (seront placées sur des shapes nommées BOOK_PHOTO_1..3 si présentes dans le template)**")
    photos = st.file_uploader("Importer jusqu'à 3 photos", type=["jpg","jpeg","png"], accept_multiple_files=True, key="bk_photos")

    book_mapping = {
        "[[BOOK_TITRE]]": st.session_state.get("bk_titre",""),
        "[[BOOK_INTRO]]": st.session_state.get("bk_intro",""),
        "[[ADRESSE]]": st.session_state.get("bien_addr",""),
        "[[NB_SURFACE]]": f"{st.session_state.get('bien_surface',0):.0f}",
        "[[NB_PIECES]]": f"{int(st.session_state.get('bien_pieces',0))}",
        "[[NB_SDB]]": f"{int(st.session_state.get('bien_sdb',0))}",
        "[[NB_COUCHAGES]]": f"{int(st.session_state.get('bien_couchages',0))}",
        "[[MODE_CHAUFFAGE]]": st.session_state.get("bien_chauffage",""),
    }

    image_by_shape = {}
    if photos:
        for idx, up in enumerate(photos[:3], start=1):
            fd, pth = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
            with open(pth, "wb") as f:
                f.write(up.getbuffer())
            image_by_shape[f"BOOK_PHOTO_{idx}"] = pth

    st.subheader("Générer le Book")
    colB1, colB2 = st.columns(2)
    with colB1:
        if st.button("Générer le Book (PPTX)"):
            tpl = resolve_book_path(chosen_book)
            if not tpl or not os.path.exists(tpl):
                st.error("Aucun template Book PPTX sélectionné. Déposez/choisissez un template ci-dessus.")
                st.stop()
            pptx_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr','bien')}.pptx")
            generate_estimation_pptx(tpl, pptx_out, book_mapping, chart_image=None, image_by_shape=image_by_shape or None)
            st.success(f"OK: {pptx_out}")
            with open(pptx_out, "rb") as f:
                st.download_button("Télécharger le PPTX", data=f.read(), file_name=os.path.basename(pptx_out))
    with colB2:
        if st.button("Générer le Book (PDF simplifié)"):
            from app.services.book_pdf import build_book_pdf
            pdf_out = os.path.join(OUT_DIR, f"Book - {st.session_state.get('bien_addr','bien')}.pdf")
            sections = []
            build_book_pdf(pdf_out, st.session_state.get("bk_titre",""), st.session_state.get("bk_intro",""), sections)
            st.success(f"OK: {pdf_out}")
            with open(pdf_out, "rb") as f:
                st.download_button("Télécharger le PDF", data=f.read(), file_name=os.path.basename(pdf_out))
