from __future__ import annotations

import re


def truncate_clean(text: str, limit: int = 250) -> str:
    cleaned_lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    cleaned = "\n".join(cleaned_lines)
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip()
    return cleaned


def sanitize_intro(text: str, address: str) -> str:
    base = (text or "").strip()
    addr = (address or "").strip()
    if addr:
        base = re.sub(re.escape(addr), "", base, flags=re.IGNORECASE)
    base = re.sub(r"\s+", " ", base).strip(" ,;-")

    starts_with_number = bool(re.match(r"^[0-9]", base))
    starts_with_addr = addr and base.lower().startswith(addr.lower())
    starts_with_symbol = base.startswith(("—", "-", "–"))
    needs_prefix = starts_with_number or starts_with_addr or starts_with_symbol
    if needs_prefix:
        remainder = base
        if starts_with_addr:
            remainder = base[len(addr) :].lstrip(" ,;-")
        else:
            remainder = re.sub(r"^[0-9]+[^A-Za-z0-9]{0,3}", "", base).lstrip(" ,;-")
        if not remainder:
            remainder = base
        cleaned = f"Dans le 17e arrondissement — {remainder.strip('— ')}"
    else:
        prefix = base.lower().startswith("quartier ") or base.lower().startswith("dans le 17e arrondissement")
        cleaned = base if prefix else f"Dans le 17e arrondissement — {base.strip('— ')}"
    return truncate_clean(cleaned, limit=280)


def sanitize_transport_lines(text: str, kind: str) -> str:
    patterns = {
        "metro": re.compile(r"^(Ligne\s+\w+|Ligne\s+\d+)\s+—"),
        "bus": re.compile(r"^(Bus\s+\d+)\s+—"),
        "taxi": re.compile(r"^(Station de taxis|Taxis:)"),
    }
    max_lines = {"metro": 4, "bus": 4, "taxi": 2}
    regex = patterns.get(kind, re.compile(r".*"))
    limit = max_lines.get(kind, 4)

    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if regex.match(stripped):
            lines.append(stripped)
        if len(lines) >= limit:
            break

    if not lines:
        if kind == "taxi":
            return "Taxis: G7/Uber disponibles (2–5 min)"
        return ""

    return truncate_clean("\n".join(lines), limit=250)
