import os, tempfile, requests
import streamlit as st

from app.services.revenue import RevenueInputs, compute_revenue
from app.services.pptx_fill import generate_estimation_pptx
from app.services.poi import fetch_transports, suggest_places
from app.services.geocode import geocode_address
from app.services.image_search import find_place_image_urls

from .utils import _sanitize_filename, list_templates

def render(config):
    TPL_DIR = config['TPL_DIR']
    EST_TPL_DIR = config['EST_TPL_DIR']
    OUT_DIR = config['OUT_DIR']

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
    radius_m = st.slider("Rayon (m)", min_value=300, max_value=3000, value=st.session_state.get("radius_m", 1200), step=100, key="radius_m")

    def _geocode_main_address():
        addr = st.session_state.get("bien_addr", "")
        if not addr:
            st.warning("Adresse introuvable…")
            return None, None
        with st.spinner("Recherche d'adresse…"):
            lat, lon = geocode_address(addr)
        if lat is None:
            st.warning("Adresse introuvable…")
        return lat, lon

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("Remplir Transports"):
            lat, lon = _geocode_main_address()
            if lat is not None:
                try:
                    tr = fetch_transports(lat, lon, radius_m=radius_m)
                    st.session_state["q_tx"] = tr.get("taxi", "")
                    st.session_state["q_metro"] = tr.get("metro", "")
                    st.session_state["q_bus"] = tr.get("bus", "")
                except Exception as e:
                    st.warning(f"Transports non chargés: {e}")
    with b2:
        if st.button("Proposer Incontournables"):
            lat, lon = _geocode_main_address()
            if lat is not None:
                try:
                    sug = suggest_places(lat, lon, radius_m=radius_m)
                    inc = sug.get("incontournables", [])
                    st.session_state["i1"] = inc[0] if len(inc) > 0 else ""
                    st.session_state["i2"] = inc[1] if len(inc) > 1 else ""
                    st.session_state["i3"] = inc[2] if len(inc) > 2 else ""
                except Exception as e:
                    st.warning(f"Suggestions non chargées: {e}")
    with b3:
        if st.button("Proposer Spots"):
            lat, lon = _geocode_main_address()
            if lat is not None:
                try:
                    sug = suggest_places(lat, lon, radius_m=radius_m)
                    sp = sug.get("spots", [])
                    st.session_state["s1"] = sp[0] if len(sp) > 0 else ""
                    st.session_state["s2"] = sp[1] if len(sp) > 1 else ""
                except Exception as e:
                    st.warning(f"Suggestions non chargées: {e}")
    with b4:
        if st.button("Proposer Lieux à visiter"):
            lat, lon = _geocode_main_address()
            if lat is not None:
                try:
                    sug = suggest_places(lat, lon, radius_m=radius_m)
                    vs = sug.get("visites", [])
                    st.session_state["v1"] = vs[0] if len(vs) > 0 else ""
                    st.session_state["v2"] = vs[1] if len(vs) > 1 else ""
                except Exception as e:
                    st.warning(f"Suggestions non chargées: {e}")

    # Points forts & Challenges (Slide 5)
    st.subheader("Points forts & Challenges (Slide 5)")
    colPF, colCH = st.columns(2)
    with colPF:
        point_fort_1 = st.text_input("Point fort 1", st.session_state.get("pf1", "Proche des transports"), key="pf1")
        point_fort_2 = st.text_input("Point fort 2", st.session_state.get("pf2", "Récemment rénové"), key="pf2")
    with colCH:
        challenge_1 = st.text_input("Challenge 1", st.session_state.get("ch1", "Pas d’ascenseur"), key="ch1")
        challenge_2 = st.text_input("Challenge 2", st.session_state.get("ch2", "Bruit de la rue en journée"), key="ch2")

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
