from __future__ import annotations

import re
from typing import List


METRO_MAX_CHARS = 90
BUS_MAX_CHARS = 90
TAXI_MAX_CHARS = 60
QUARTIER_MAX_CHARS = 200

METRO_MAX_LINES = 3
BUS_MAX_LINES = 3
TAXI_MAX_LINES = 1


def normalize_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def compact_line(line: str) -> str:
    compacted = line
    compacted = compacted.replace("Ligne ", "L")
    compacted = compacted.replace("Station ", "")
    compacted = compacted.replace("Arrêt ", "")
    compacted = compacted.replace(" à pied", "")
    compacted = compacted.replace("minutes", "min")
    compacted = compacted.translate(str.maketrans("", "", ",.;:!?"))
    compacted = re.sub(r"\s+", " ", compacted)
    return compacted.strip()


def _truncate_with_ellipsis(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars == 1:
        return "…"
    return text[: max_chars - 1].rstrip() + "…"


def enforce_limits(text: str, max_chars: int, max_lines: int) -> str:
    lines = normalize_lines(text)
    lines = [compact_line(l) for l in lines]
    lines = lines[:max_lines]

    joined = "\n".join(lines)
    if len(joined) <= max_chars:
        return joined

    if len(lines) > 2:
        joined = "\n".join(lines[:2])
    if len(joined) <= max_chars and len(lines) > 2:
        return joined

    if len(lines) > 1:
        joined = lines[0]
    if len(joined) <= max_chars:
        return joined

    return _truncate_with_ellipsis(joined, max_chars)
