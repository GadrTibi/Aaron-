import re
from typing import Iterable, Iterator

from docx import Document
from pptx import Presentation


DOCX_TOKEN_PATTERN = re.compile(r"«[^»]+»")
PPTX_TOKEN_PATTERN = re.compile(r"\[\[[^\]]+\]\]")


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


def extract_docx_tokens(template_path: str) -> set[str]:
    """Retourne les tokens DOCX présents dans un fichier.

    Les tokens peuvent être fragmentés sur plusieurs *runs* Word ; la
    concaténation des runs de chaque paragraphe permet de les détecter
    correctement.
    """

    doc = Document(template_path)
    return extract_docx_tokens_from_document(doc)


def walk_pptx_shapes(shapes) -> Iterator[object]:
    """Yield all shapes recursively, diving into groups if present."""

    for sh in shapes:
        yield sh
        if hasattr(sh, "shapes"):
            yield from walk_pptx_shapes(sh.shapes)


def _collect_pptx_paragraph_tokens(paragraph, pattern: re.Pattern[str]) -> set[str]:
    txt = "".join(run.text or "" for run in paragraph.runs)
    return set(pattern.findall(txt))


def extract_pptx_tokens_from_presentation(prs: Presentation) -> set[str]:
    tokens: set[str] = set()
    for slide in prs.slides:
        for sh in walk_pptx_shapes(slide.shapes):
            if hasattr(sh, "text_frame") and sh.text_frame:
                for para in sh.text_frame.paragraphs:
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
