import re
from typing import Iterable, Iterator

from docx import Document
from pptx import Presentation


DOCX_TOKEN_PATTERN = re.compile(r"«[^»]+»")
PPTX_TOKEN_PATTERN = re.compile(r"\[\[[^\]]+\]\]")

# Mapping of legacy/alternative tokens to their canonical counterparts.
TOKEN_ALIASES: dict[str, str] = {
    "[[METRO]]": "[[TRANSPORTS_METRO_TEXTE]]",
    "[[METRO_TEXTE]]": "[[TRANSPORTS_METRO_TEXTE]]",
    "[[TRANSPORT_METRO_TEXTE]]": "[[TRANSPORTS_METRO_TEXTE]]",
    "[[BUS]]": "[[TRANSPORTS_BUS_TEXTE]]",
    "[[BUS_TEXTE]]": "[[TRANSPORTS_BUS_TEXTE]]",
    "[[TRANSPORT_BUS_TEXTE]]": "[[TRANSPORTS_BUS_TEXTE]]",
    "[[TAXI]]": "[[TRANSPORTS_TAXI_TEXTE]]",
    "[[TAXI_TEXTE]]": "[[TRANSPORTS_TAXI_TEXTE]]",
    "[[QUARTIER]]": "[[QUARTIER_INTRO]]",
}


def _collect_docx_paragraph_tokens(paragraph, pattern: re.Pattern[str]) -> set[str]:
    txt = "".join(run.text or "" for run in paragraph.runs)
    return set(pattern.findall(txt))


def extract_docx_tokens_from_document(doc: Document) -> set[str]:
    tokens: set[str] = set()

    def collect(paragraph) -> None:
        tokens.update(_collect_docx_paragraph_tokens(paragraph, DOCX_TOKEN_PATTERN))

    for p in doc.paragraphs:
        collect(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    collect(p)
    return tokens


def walk_pptx_shapes(shapes) -> Iterator[object]:
    """Yield all shapes recursively, diving into groups if present."""

    for sh in shapes:
        yield sh
        if hasattr(sh, "shapes"):
            yield from walk_pptx_shapes(sh.shapes)


def iter_shape_paragraphs(shape) -> Iterator[object]:
    """Yield all paragraphs for a given shape, including table cells."""

    if hasattr(shape, "text_frame") and shape.text_frame:
        yield from shape.text_frame.paragraphs
    if getattr(shape, "has_table", False):
        table = getattr(shape, "table", None)
        if table:
            for row in table.rows:
                for cell in row.cells:
                    text_frame = getattr(cell, "text_frame", None)
                    if text_frame:
                        yield from text_frame.paragraphs


def _collect_pptx_paragraph_tokens(paragraph, pattern: re.Pattern[str]) -> set[str]:
    txt = "".join(run.text or "" for run in paragraph.runs)
    return set(pattern.findall(txt))


def extract_pptx_tokens_from_presentation(prs: Presentation) -> set[str]:
    tokens: set[str] = set()
    for slide in prs.slides:
        for sh in walk_pptx_shapes(slide.shapes):
            for para in iter_shape_paragraphs(sh):
                tokens.update(_collect_pptx_paragraph_tokens(para, PPTX_TOKEN_PATTERN))
    return tokens


def extract_shape_names(shapes: Iterable[object]) -> set[str]:
    names: set[str] = set()
    for sh in walk_pptx_shapes(shapes):
        name = getattr(sh, "name", None)
        if name:
            norm = name.strip()
            if norm:
                names.add(norm)
    return names


def apply_token_aliases(mapping: dict[str, str], tokens_in_template: set[str]) -> dict[str, str]:
    """
    Enrichit `mapping` avec les alias présents dans le template.

    Retourne un dictionnaire {alias: cible} pour les alias effectivement appliqués.
    """
    applied: dict[str, str] = {}
    for alias, target in TOKEN_ALIASES.items():
        if alias in tokens_in_template and alias not in mapping and target in mapping:
            mapping[alias] = mapping[target]
            applied[alias] = target
    return applied


def extract_pptx_tokens(template_path: str) -> set[str]:
    prs = Presentation(template_path)
    return extract_pptx_tokens_from_presentation(prs)
