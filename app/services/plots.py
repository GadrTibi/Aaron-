import logging
import os
from typing import List

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

LOGGER = logging.getLogger(__name__)

BACKGROUND = "#FBF8E4"
BAR_COLOR = "#033E41"
GRID_COLOR = "#44706D"

LABELS: List[str] = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre 1 à 7",
    "Septembre 8 à 30",
    "Octobre",
    "Novembre",
    "Décembre",
]

SEASONALITY: List[float] = [
    0.75,
    0.75,
    0.85,
    0.9,
    1.1,
    1.25,
    1.2,
    1.0,
    1.0,
    1.2,
    1.25,
    0.75,
    1.0,
]


def _resolve_font() -> str:
    for candidate in ("Calibri", "DejaVu Sans"):
        try:
            font_manager.findfont(candidate, fallback_to_default=False)
            return candidate
        except Exception:
            continue
    return "DejaVu Sans"


FONT_NAME = _resolve_font()


def _format_euro_axis(value: float, _pos) -> str:
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s}\u00A0€"


def _format_int_euro(value: float) -> str:
    return f"{int(round(value))}€"


def _plots_output_dir() -> str:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_dir = os.path.join(base_dir, "out", "plots")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def build_estimation_histo(base_nightly_price: float) -> str:
    """Generate the estimation histogram and return the PNG path."""
    if base_nightly_price is None:
        raise ValueError("Paramètre 'base_nightly_price' introuvable pour générer le graphique.")

    try:
        price = float(base_nightly_price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Valeur 'base_nightly_price' invalide pour le graphique.") from exc

    evo_price = [price * s for s in SEASONALITY]
    LOGGER.info("Génération du graphique Estimation Histo (%s)", price)

    fig, ax = plt.subplots(figsize=(12, 6), dpi=220)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)

    indices = range(len(LABELS))
    bars = ax.bar(indices, evo_price, width=0.60, color=BAR_COLOR, edgecolor=BAR_COLOR, linewidth=0)

    ax.set_xticks(list(indices))
    ax.set_xticklabels(LABELS, rotation=45, ha="right", va="top", fontsize=11, color=BAR_COLOR)
    for label in ax.get_xticklabels():
        label.set_fontname(FONT_NAME)

    ax.tick_params(axis="x", colors=BAR_COLOR)
    ax.tick_params(axis="y", colors=BAR_COLOR, labelsize=11)
    for label in ax.get_yticklabels():
        label.set_fontname(FONT_NAME)

    ax.yaxis.grid(True, which="major", linestyle="-", linewidth=1.0, color=GRID_COLOR, alpha=0.25)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_linewidth(1.0)
    ax.spines["bottom"].set_alpha(0.6)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["left"].set_alpha(0.25)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.yaxis.set_major_formatter(FuncFormatter(_format_euro_axis))

    ax.bar_label(
        bars,
        labels=[_format_int_euro(v) for v in evo_price],
        padding=3,
        color=BAR_COLOR,
        fontsize=11,
        fontweight="bold",
    )

    for txt in ax.texts:
        txt.set_fontname(FONT_NAME)

    plt.margins(x=0.02)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.25)

    out_path = os.path.join(_plots_output_dir(), "estimation_histo.png")
    fig.savefig(out_path, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(fig)

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError("Échec de la génération du graphique Estimation (fichier vide).")

    LOGGER.info("Graphique Estimation enregistré: %s", out_path)
    return out_path
