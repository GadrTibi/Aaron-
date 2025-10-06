from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


LOGGER = logging.getLogger(__name__)


def _format_euro(value: float) -> str:
    """Return a French formatted euro amount with up to one decimal."""

    if math.isclose(value, round(value), rel_tol=1e-9, abs_tol=1e-9):
        formatted = f"{int(round(value)):,}".replace(",", " ")
    else:
        formatted = f"{value:,.1f}".replace(",", " ").replace(".", ",")
    if "," not in formatted and " " not in formatted:
        # Ensure decimal separator is French comma even for thousands < 1000
        formatted = formatted.replace(".", ",")
    return f"{formatted} €"


def build_estimation_histo(base_nightly_price: float) -> str:
    """Generate the estimation histogram plot and return its path."""

    if base_nightly_price is None:
        raise ValueError("Paramètre 'base_nightly_price' manquant pour la génération du graphique.")

    try:
        base_price = float(base_nightly_price)
    except (TypeError, ValueError) as exc:  # pragma: no cover - guardrail
        raise ValueError("Paramètre 'base_nightly_price' invalide pour la génération du graphique.") from exc

    labels: List[str] = [
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
    seasonality = [
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
    evo_price = [base_price * s for s in seasonality]

    output_dir = Path("out/plots")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "estimation_histo.png"

    plt.rcParams["font.family"] = ["Calibri", "DejaVu Sans"]
    fig, ax = plt.subplots(figsize=(12, 6), dpi=220)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    x_positions = range(len(labels))
    bars = ax.bar(
        x_positions,
        evo_price,
        color="#2F5597",
        edgecolor="#1F3A6D",
        linewidth=1.0,
        width=0.75,
    )

    ax.set_title(
        "Évo du prix/nuitée",
        fontdict={"fontsize": 14, "fontweight": "bold", "color": "#1F1F1F"},
        loc="left",
    )
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels(labels, rotation=45, ha="right", va="top", fontsize=11)
    ax.tick_params(axis="y", labelsize=11, colors="#1F1F1F")
    ax.tick_params(axis="x", colors="#1F1F1F")
    ax.margins(x=0.02)

    formatter = FuncFormatter(lambda value, _: _format_euro(value))
    ax.yaxis.set_major_formatter(formatter)
    ax.grid(axis="y", color="#D9D9D9", linestyle="-", linewidth=0.8)
    ax.set_axisbelow(True)

    for spine in ("top", "right"):
        ax.spines[spine].set_alpha(0.2)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#1F1F1F")
        ax.spines[spine].set_linewidth(0.8)

    for rect, value in zip(bars, evo_price):
        ax.annotate(
            _format_euro(value).replace(".", ","),
            xy=(rect.get_x() + rect.get_width() / 2, rect.get_height()),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            color="#1F1F1F",
        )

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.25)

    fig.savefig(output_path, bbox_inches="tight", facecolor="#FFFFFF")
    plt.close(fig)

    LOGGER.info("Graphique estimation généré: %s", output_path)
    return str(output_path)

