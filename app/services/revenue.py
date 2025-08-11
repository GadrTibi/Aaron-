from dataclasses import dataclass

@dataclass
class RevenueInputs:
    prix_nuitee: float
    taux_occupation_pct: float
    commission_pct: float  # commission MFY
    frais_menage_mensuels: float

def compute_revenue(inp: RevenueInputs):
    jours_occupes = 30.0 * (inp.taux_occupation_pct / 100.0)
    revenu_brut = inp.prix_nuitee * jours_occupes
    frais_commission = revenu_brut * (inp.commission_pct / 100.0)
    frais_generaux = frais_commission + inp.frais_menage_mensuels
    revenu_net = max(revenu_brut - frais_generaux, 0.0)
    return {
        "jours_occupes": jours_occupes,
        "revenu_brut": revenu_brut,
        "frais_generaux": frais_generaux,
        "revenu_net": revenu_net,
    }