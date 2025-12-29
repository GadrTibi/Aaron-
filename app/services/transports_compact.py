from __future__ import annotations

import re
from typing import Iterable


def _normalize_raw(raw: str) -> str:
    text = (raw or "").lower()
    text = text.replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _is_duration_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 3) : min(len(text), end + 5)]
    return "min" in window


def extract_metro_lines(raw: str) -> list[str]:
    """
    Extrait les lignes de métro (1-14 + 3bis/7bis) et options RER/Tram.
    """

    normalized = _normalize_raw((raw or "").replace("métro", "metro"))
    if not normalized:
        return []

    chunks = re.split(r"[.;\n]+", normalized)
    pattern = re.compile(
        r"\b(?P<rer>rer\s*[a-e])\b|"
        r"\b(?P<tram>t\s*(?P<tram_num>\d{1,2})(?P<tram_suffix>[ab]?))\b|"
        r"\b(?:ligne\s*)?(?P<metro>(?:3\s*bis|7\s*bis|1[0-4]|[1-9]))\b",
        re.IGNORECASE,
    )

    lines: list[str] = []
    for chunk in chunks:
        if not any(keyword in chunk for keyword in ("metro", "métro", "ligne", "rer", "t")):
            continue
        for match in pattern.finditer(chunk):
            start, end = match.span()
            if _is_duration_context(chunk, start, end):
                continue
            line: str | None = None
            if match.group("rer"):
                letter = match.group("rer").split()[-1]
                line = f"RER {letter.upper()}"
            elif match.group("tram"):
                suffix = match.group("tram_suffix") or ""
                suffix = suffix.lower()
                line = f"T{match.group('tram_num')}{suffix}"
            else:
                metro_raw = match.group("metro")
                if metro_raw:
                    metro_clean = metro_raw.replace(" ", "")
                    line = metro_clean
            if line:
                lines.append(line)

    if not lines:
        for match in pattern.finditer(normalized):
            start, end = match.span()
            if _is_duration_context(normalized, start, end):
                continue
            line: str | None = None
            if match.group("rer"):
                letter = match.group("rer").split()[-1]
                line = f"RER {letter.upper()}"
            elif match.group("tram"):
                suffix = match.group("tram_suffix") or ""
                suffix = suffix.lower()
                line = f"T{match.group('tram_num')}{suffix}"
            else:
                metro_raw = match.group("metro")
                if metro_raw:
                    metro_clean = metro_raw.replace(" ", "")
                    line = metro_clean
            if line:
                lines.append(line)

    return _dedupe_preserve_order(lines)


def extract_bus_lines(raw: str) -> list[str]:
    normalized = _normalize_raw(raw)
    if not normalized:
        return []

    chunks = re.split(r"[.;\n]+", normalized)
    lines: list[str] = []
    for chunk in chunks:
        if not any(keyword in chunk for keyword in ("bus", "ligne", "lignes")):
            continue
        for match in re.finditer(r"\b(\d{1,3})\b", chunk):
            start, end = match.span()
            if _is_duration_context(chunk, start, end):
                continue
            number = int(match.group(1))
            if number < 1 or number > 399:
                continue
            lines.append(str(number))

    if not lines:
        for match in re.finditer(r"\b(\d{1,3})\b", normalized):
            start, end = match.span()
            if _is_duration_context(normalized, start, end):
                continue
            number = int(match.group(1))
            if number < 1 or number > 399:
                continue
            lines.append(str(number))

    return _dedupe_preserve_order(lines)


def format_compact_lines(prefix: str, lines: list[str], max_items: int) -> str:
    if not lines:
        return ""
    kept = lines[:max_items]
    suffix = "…" if len(lines) > max_items else ""
    joined = ", ".join(kept)
    prefix_clean = prefix.strip()
    if prefix_clean:
        return f"{prefix_clean} {joined}{suffix}"
    return f"{joined}{suffix}"


def build_compact_transport_texts(metro_raw: str, bus_raw: str, taxi_raw: str) -> dict[str, str]:
    metro_lines = extract_metro_lines(metro_raw)
    bus_lines = extract_bus_lines(bus_raw)

    taxi_clean = (taxi_raw or "").strip()
    taxi_normalized = _normalize_raw(taxi_clean)
    taxi = "Stations de taxi" if not taxi_normalized or "taxi" not in taxi_normalized else "Stations de taxi"

    metro_text = format_compact_lines("Métro, ligne", metro_lines, max_items=4)
    bus_text = format_compact_lines("Bus, ligne", bus_lines, max_items=6)

    return {
        "transport_metro_texte": metro_text,
        "transport_bus_texte": bus_text,
        "transport_taxi_texte": taxi,
    }
