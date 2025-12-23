from pathlib import Path

from docx import Document

from app.services.template_validation import validate_docx_template


def test_validate_docx_template_flags_unknown_token(tmp_path: Path) -> None:
    doc = Document()
    doc.add_paragraph("Bonjour «TOKEN_INCONNU»")
    path = tmp_path / "template.docx"
    doc.save(path)

    result = validate_docx_template(str(path), {"«TOKEN_CONNU»"})

    assert result.severity == "WARN"
    assert not result.missing_required_shapes
    assert "«TOKEN_INCONNU»" in result.unknown_tokens_in_template
    assert result.ok
