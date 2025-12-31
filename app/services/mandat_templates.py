from __future__ import annotations

from typing import Iterable

from app.services.template_catalog import TemplateItem


def filter_mandat_templates(templates: Iterable[TemplateItem], mandat_type: str) -> list[TemplateItem]:
    """Filtre les templates de mandat selon le type sélectionné (CD/MD).

    - MD : libellé contenant ``MD`` (case-insensitive) ou ``bail mobilité``.
    - CD : libellé contenant ``CD`` ou ``courte durée``.
    """

    normalized = mandat_type.strip().lower() if mandat_type else ""
    if "md" in normalized:
        needles = ["md", "bail mobilité"]
    else:
        needles = ["cd", "courte durée"]

    filtered = []
    for tpl in templates:
        label = tpl.label.lower()
        if any(needle in label for needle in needles):
            filtered.append(tpl)
    return filtered
