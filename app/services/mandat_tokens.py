from datetime import date
from typing import Optional


def _bool_oui_non(v) -> str:
    if isinstance(v, str):
        v = v.strip().lower()
        if v in ("oui", "yes", "true", "1"):
            return "Oui"
        if v in ("non", "no", "false", "0"):
            return "Non"
    return "Oui" if bool(v) else "Non"


def build_mandat_mapping(ss: dict, signature_date: Optional[date] = None) -> dict:
    """Construit le mapping {token_docx: valeur} pour le mandat.

    Les valeurs priorisent ``ss[...]`` provenant des Données générales et
    n'exposent pas de redondance à l'UI.
    """
    # Données générales (déjà présentes ailleurs dans l'app)
    addr_bien = ss.get("bien_addr", "")
    surface = ss.get("bien_surface", "")
    nb_pieces = ss.get("bien_pieces", "")
    nb_sdb = ss.get("bien_sdb", "")
    nb_couch = ss.get("bien_couchages", "")
    chauffage = ss.get("bien_chauffage", "")
    eau_chaude = ss.get("bien_eau_chaude", ss.get("bien_eau_chaude_mode", ""))

    # Proprio (saisis ailleurs, sinon l'UI Mandat complète)
    forme_prop = ss.get("owner_forme", ss.get("own_forme", ""))
    nom_prop = ss.get("owner_nom", ss.get("own_nom", ""))
    prenom_prop = ss.get("owner_prenom", ss.get("own_prenom", ""))
    adr_prop = ss.get("owner_adresse", ss.get("own_addr", ""))
    cp_prop = ss.get("owner_cp", ss.get("own_cp", ""))
    ville_prop = ss.get("owner_ville", ss.get("own_ville", ""))
    mail_prop = ss.get("owner_email", ss.get("own_email", ""))

    # Compléments spécifiques Mandat (UI Mandat uniquement)
    type_peau = ss.get("mandat_type_pieces_eau", "Salle(s) d’eau")
    dest_bien = ss.get("mandat_destination_bien", "")
    animaux = _bool_oui_non(ss.get("mandat_animaux_autorises", False))
    commission = ss.get("mandat_commission_pct", ss.get("rn_comm", ""))
    date_debut = ss.get("mandat_date_debut", "")
    if isinstance(date_debut, date):
        date_debut = date_debut.strftime("%d/%m/%Y")
    remise_pj = ss.get("mandat_remise_pieces", "")

    # Date de signature du mandat : fallback sur aujourd'hui pour éviter les tokens non remplacés
    sig_date = signature_date or ss.get("mandat_signature_date") or date.today()
    if not isinstance(sig_date, date):
        sig_date = date.today()

    jour_str = str(sig_date.day)
    mois_fr = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    mois_annee_str = f"{mois_fr[sig_date.month - 1]} {sig_date.year}"
    date_full_str = f"{jour_str} {mois_annee_str}"

    # Normalisations chiffre → str
    def fmt_int(v):
        try:
            return f"{int(v)}"
        except Exception:
            return f"{v}" if v not in (None, "") else ""

    mapping = {
        # Partie entête / parties
        "«Forme_du_propriétaire»": forme_prop,
        "«Nom_du_propriétaire»": nom_prop,
        "«Prénom_du_propriétaire»": prenom_prop,
        "«Adresse_du_propriétaire»": adr_prop,
        "«Code_postal_du_propriétaire»": cp_prop,
        "«Ville_du_propriétaire»": ville_prop,
        "«Mail_du_propriétaire»": mail_prop,

        # Bien / adresse
        "«Adresse_du_bien_loué»": addr_bien,

        # Article 1 – Désignation
        "«Surface_totale_du_bien»": fmt_int(surface),
        "«Nombre_de_pièces_du_bien»": fmt_int(nb_pieces),
        "«Nombre_de_pièces_deau»": fmt_int(nb_sdb),
        "«Type_de_pièces_deau»": type_peau,
        "«Nombre_de_pax»": fmt_int(nb_couch),

        # Article 2 – Équipements
        "«Mode_de_production_de_chauffage»": chauffage,
        "«Mode_de_production_deau_chaude_sanitair»": eau_chaude,

        # Article 3/4 – Activité / Déclarations
        "«Destination_du_bien»": dest_bien,

        # Article 5 – Durée
        "«Date_de_début_de_mandat»": date_debut,

        # Article 6 – Conditions / divers
        "«Animaux_autorisés»": animaux,

        # Article 7 – Rémunérations
        "«M__de_rémunération_MFY»": fmt_int(commission),

        # Article 16 – Remise de pièces
        "«Remise_de_pièces»": remise_pj,

        # Bas de page – Date de signature du mandat
        "«MANDAT_DATE_SIGNATURE»": mois_annee_str,
        "«MANDAT_JOUR_SIGNATURE»": jour_str,
        "MANDAT_JOUR_SIGNATURE": jour_str,
        "MANDAT_DATE_SIGNATURE": mois_annee_str,
        "MANDAT_DATE_SIGNATURE_FULL": date_full_str,
    }
    # Tests manuels recommandés :
    # 1. Ouvrir la page Mandat, renseigner les champs et choisir une date de signature.
    # 2. Générer le DOCX Mandat puis l'ouvrir.
    # 3. Vérifier que «MANDAT_JOUR_SIGNATURE» et «MANDAT_DATE_SIGNATURE» sont remplacés
    #    (ex. «Fait à Paris, le 12 mai 2025»), et que les autres tokens restent fonctionnels.
    return mapping
