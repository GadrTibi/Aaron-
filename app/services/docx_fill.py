import os
import re
from typing import Dict

from docx import Document


def _replace_in_paragraph(paragraph, mapping: Dict[str, str]) -> None:
    def rebuild():
        segs = [(i, r.text or "") for i, r in enumerate(paragraph.runs)]
        joined = "".join(t for _, t in segs)
        return segs, joined

    for key, val in mapping.items():
        while True:
            segs, text = rebuild()
            idx = text.find(key)
            if idx < 0:
                break
            pos = 0
            start_run = start_off = end_run = end_off = 0
            for i, t in segs:
                if idx >= pos and idx <= pos + len(t):
                    start_run = i
                    start_off = idx - pos
                    break
                pos += len(t)
            pos = 0
            end_idx = idx + len(key)
            for i, t in segs:
                if end_idx > pos and end_idx <= pos + len(t):
                    end_run = i
                    end_off = end_idx - pos
                    break
                pos += len(t)
            sr = paragraph.runs[start_run]
            pre = sr.text[:start_off]
            sr.text = pre + val
            for ridx in range(start_run + 1, end_run):
                paragraph.runs[ridx].text = ""
            if end_run != start_run:
                lr = paragraph.runs[end_run]
                suffix = lr.text[end_off:]
                lr.text = suffix


def _replace_in_document(doc, mapping: Dict[str, str]) -> None:
    for p in doc.paragraphs:
        _replace_in_paragraph(p, mapping)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _replace_in_paragraph(p, mapping)


def replace_placeholders_docx(template_path: str, output_path: str, mapping: Dict[str, str]) -> None:
    doc = Document(template_path)
    _replace_in_document(doc, mapping)
    doc.save(output_path)


def generate_docx_from_template(template_path: str, output_path: str, mapping: Dict[str, str]) -> None:
    """Génère un DOCX en remplaçant les tokens et signale ceux restants."""
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template DOCX introuvable: {template_path}")
    doc = Document(template_path)
    _replace_in_document(doc, mapping)

    pat = re.compile(r"«[^»]+»")
    leftovers = set()

    def collect(paragraph) -> None:
        txt = "".join(r.text for r in paragraph.runs)
        leftovers.update(pat.findall(txt))

    for p in doc.paragraphs:
        collect(p)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    collect(p)

    doc.save(output_path)
    if leftovers:
        print("[WARN] Tokens non remplacés (mandat):", sorted(leftovers))
