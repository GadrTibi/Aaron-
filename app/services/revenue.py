from dataclasses import dataclass
from typing import Mapping


ESTIMATION_DAYS_PER_MONTH_CD = 25.5
ESTIMATION_DAYS_PER_MONTH_MD = 26.0


@dataclass
class RevenueInputs:
    prix_nuitee: float
    taux_occupation_pct: float
    platform_fee_pct: float
    mfy_commission_pct: float
    frais_menage_mensuels: float


def format_eur(value: float) -> str:
    return f"{value:.0f} €"


def _format_pct(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def compute_revenue(inp: RevenueInputs, *, days_per_month: float = 30.0):
    jours_occupes = float(days_per_month) * (inp.taux_occupation_pct / 100.0)
    revenu_brut = inp.prix_nuitee * jours_occupes

    platform_fee_eur = revenu_brut * (inp.platform_fee_pct / 100.0)
    base_commission = max(revenu_brut - platform_fee_eur, 0.0)
    mfy_commission_eur = base_commission * (inp.mfy_commission_pct / 100.0)
    cleaning_fee_eur = inp.frais_menage_mensuels

    frais_generaux = platform_fee_eur + mfy_commission_eur + cleaning_fee_eur
    revenu_net = max(revenu_brut - frais_generaux, 0.0)
    return {
        "jours_occupes": jours_occupes,
        "revenu_brut": revenu_brut,
        "frais_generaux": frais_generaux,
        "revenu_net": revenu_net,
        "platform_fee_pct": inp.platform_fee_pct,
        "platform_fee_eur": platform_fee_eur,
        "base_commission": base_commission,
        "mfy_commission_pct": inp.mfy_commission_pct,
        "mfy_commission_eur": mfy_commission_eur,
        "cleaning_fee_eur": cleaning_fee_eur,
    }


def build_revenue_token_mapping(calc: Mapping[str, float]) -> dict[str, str]:
    revenu_brut = float(calc.get("revenu_brut", 0.0))
    frais_generaux = float(calc.get("frais_generaux", 0.0))
    revenu_net = float(calc.get("revenu_net", 0.0))
    jours_occupes = float(calc.get("jours_occupes", 0.0))
    platform_fee_pct = float(calc.get("platform_fee_pct", 0.0))
    platform_fee_eur = float(calc.get("platform_fee_eur", 0.0))
    cleaning_fee_eur = float(calc.get("cleaning_fee_eur", 0.0))
    mfy_commission_pct = float(calc.get("mfy_commission_pct", 0.0))
    mfy_commission_eur = float(calc.get("mfy_commission_eur", 0.0))

    return {
        "[[REV_BRUT]]": format_eur(revenu_brut),
        "[[FRAIS_GEN]]": format_eur(frais_generaux),
        "[[REV_NET]]": format_eur(revenu_net),
        "[[JOURS_OCC]]": f"{jours_occupes:.1f} j",
        "[[PLATFORM_FEE_PCT]]": _format_pct(platform_fee_pct),
        "[[PLATFORM_FEE_EUR]]": format_eur(platform_fee_eur),
        "[[CLEANING_FEE_EUR]]": format_eur(cleaning_fee_eur),
        "[[MFY_COMMISSION_PCT]]": _format_pct(mfy_commission_pct),
        "[[MFY_COMMISSION_EUR]]": format_eur(mfy_commission_eur),
    }
