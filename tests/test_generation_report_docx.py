import sys
from pathlib import Path

from docx import Document

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.docx_fill import generate_docx_from_template


def test_generation_report_collects_missing_tokens(tmp_path):
    template_path = tmp_path / "template.docx"
    output_path = tmp_path / "out.docx"

    doc = Document()
    doc.add_paragraph("Bonjour «TOKEN_MANQUANT»")
    doc.save(template_path)

    report = generate_docx_from_template(str(template_path), str(output_path), mapping={})

    assert output_path.exists()
    assert "«TOKEN_MANQUANT»" in report.missing_tokens
    assert report.ok is True
