from __future__ import annotations

import re
from typing import Iterable

METRO_MAX_CHARS = 90
BUS_MAX_CHARS = 90
TAXI_MAX_CHARS = 60
QUARTIER_MAX_CHARS = 200

METRO_MAX_LINES = 3
BUS_MAX_LINES = 3
TAXI_MAX_LINES = 1


def normalize_lines(text: str) -> list[str]:
    """Split text into non-empty, stripped lines."""

    parts = text.splitlines()
    cleaned = [part.strip() for part in parts]
    return [part for part in cleaned if part]


def _substitute(text: str, pattern: str, repl: str) -> str:
    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def compact_line(line: str) -> str:
    """Shorten a transport line label using common substitutions."""

    text = line.strip()
    substitutions: Iterable[tuple[str, str]] = (
        (r"\bligne\s+", "L"),
        (r"\bstation\s+", ""),
        (r"\barr[êe]t\s+", ""),
        (r"\s+à pied\b", ""),
        (r"\bminutes?\b", "min"),
    )
    for pattern, repl in substitutions:
        text = _substitute(text, pattern, repl)

    # Simplify punctuation and separators
    text = re.sub(r"[()]", "", text)
    text = re.sub(r"[–—−]+", "-", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"[,:;]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -\t\r\n")


def enforce_limits(text: str, max_chars: int, max_lines: int) -> str:
    """Normalize, compact and trim text to fit character and line limits."""

    lines = normalize_lines(text)
    lines = [compact_line(line) for line in lines if line]
    lines = lines[:max_lines]

    def _join(candidate: list[str]) -> str:
        return "\n".join(candidate)

    joined = _join(lines)
    if len(joined) > max_chars:
        for target in (2, 1):
            if len(lines) > target:
                candidate = _join(lines[:target])
                if len(candidate) <= max_chars:
                    joined = candidate
                    break
                joined = candidate
        if len(joined) > max_chars:
            cutoff = max(max_chars - 1, 0)
            trimmed = joined[:cutoff].rstrip()
            joined = f"{trimmed}…" if cutoff else "…"
    return joined
