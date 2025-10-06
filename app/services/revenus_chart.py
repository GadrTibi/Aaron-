"""Utilities for loading revenue chart data and rendering bar charts."""
from __future__ import annotations

import logging
import os
import re
from typing import Sequence, Tuple

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd

LOGGER = logging.getLogger(__name__)

_COLUMN_RE = re.compile(r"^(?P<col>[A-Z]+)(?P<row>\d+)$", re.IGNORECASE)


def _column_letters_to_index(col_letters: str) -> int:
    """Convert Excel column letters (A, B, ..., AA, AB, ...) to a 0-based index."""
    col_letters = col_letters.strip().upper()
    if not col_letters.isalpha():
        raise ValueError(f"Invalid column label: {col_letters}")
    index = 0
    for char in col_letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def parse_excel_range(range_str: str) -> Tuple[int, int, int]:
    """Parse an Excel range like "B4:N4" into 0-based (row, col_start, col_end).

    The range must refer to a single row. If only one cell is provided (e.g. "C5"),
    col_start and col_end will be identical.
    """
    if not range_str or not isinstance(range_str, str):
        raise ValueError("range_str must be a non-empty string")

    parts = [p.strip() for p in range_str.split(":") if p.strip()]
    if not parts:
        raise ValueError(f"Invalid range: {range_str}")
    if len(parts) == 1:
        parts = [parts[0], parts[0]]

    match_start = _COLUMN_RE.match(parts[0])
    match_end = _COLUMN_RE.match(parts[1])
    if not match_start or not match_end:
        raise ValueError(f"Invalid range: {range_str}")

    row_start = int(match_start.group("row")) - 1
    row_end = int(match_end.group("row")) - 1
    if row_start != row_end:
        raise ValueError("Only single-row ranges are supported for charts")

    col_start = _column_letters_to_index(match_start.group("col"))
    col_end = _column_letters_to_index(match_end.group("col"))
    if col_start > col_end:
        col_start, col_end = col_end, col_start

    return row_start, col_start, col_end


def _clean_numeric_series(values: Sequence) -> pd.Series:
    series = pd.Series(list(values))
    if series.empty:
        return series.astype(float)
    series = series.astype(str)
    series = series.str.replace("€", "", regex=False)
    series = series.str.replace("\u202f", " ", regex=False)
    series = series.str.replace("\xa0", " ", regex=False)
    series = series.str.replace(" ", "", regex=False)
    series = series.str.replace(",", ".", regex=False)
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return numeric


def load_series_from_excel(
    file_like_or_path,
    sheet: str,
    x_range: str,
    y_range: str,
) -> Tuple[list[str], list[float]]:
    """Load labels and numeric values from an Excel worksheet."""
    if hasattr(file_like_or_path, "seek"):
        file_like_or_path.seek(0)
    df = pd.read_excel(file_like_or_path, sheet_name=sheet, header=None)

    x_row, x_col_start, x_col_end = parse_excel_range(x_range)
    y_row, y_col_start, y_col_end = parse_excel_range(y_range)

    labels = df.iloc[x_row, x_col_start : x_col_end + 1]
    values = df.iloc[y_row, y_col_start : y_col_end + 1]

    if len(labels) != len(values):
        raise ValueError("X and Y ranges must have the same length")

    label_list = ["" if pd.isna(x) else str(x) for x in labels.tolist()]
    numeric_values = _clean_numeric_series(values.tolist()).astype(float).tolist()
    return label_list, numeric_values


def _format_currency(value: float) -> str:
    formatted = f"{value:,.2f}"  # e.g., 1,234.56
    formatted = formatted.replace(",", " ")
    formatted = formatted.replace(".", ",")
    return f"{formatted} €"


def render_chart_png(
    labels: Sequence[str],
    values: Sequence[float],
    out_path: str,
    *,
    bar_color: str = "#0E4A4F",
    dpi: int = 220,
) -> None:
    """Render a revenue chart into a transparent PNG file."""
    if len(labels) != len(values):
        raise ValueError("Labels and values must have the same length")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    numeric_values = [float(v) for v in values]
    x_positions = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    ax.bar(x_positions, numeric_values, color=bar_color, width=0.65)
    ax.yaxis.grid(True, alpha=0.2)
    ax.set_axisbelow(True)

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
    ax.tick_params(axis="y", labelsize=10)

    formatter = FuncFormatter(lambda val, _: _format_currency(val))
    ax.yaxis.set_major_formatter(formatter)

    max_value = max(numeric_values) if numeric_values else 0
    if max_value <= 0:
        ax.set_ylim(0, 1)
    else:
        ax.set_ylim(0, max_value * 1.15)

    padding = max_value * 0.02 if max_value else 0.1
    for idx, val in enumerate(numeric_values):
        rounded = int(round(float(val)))
        ax.text(
            idx,
            val + padding,
            f"{rounded}€",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", transparent=True)
    plt.close(fig)
    LOGGER.debug("Chart saved to %s", out_path)
