from pathlib import Path

from app.services.mandat_templates import filter_mandat_templates
from app.services.template_catalog import TemplateItem


def _tpl(label: str) -> TemplateItem:
    return TemplateItem(label=label, source="repo", path=Path(label))


def test_filter_md_templates_prefers_md_labels():
    templates = [
        _tpl("Mandat CD.docx"),
        _tpl("mandat_md.docx"),
        _tpl("Bail mobilité mandat.docx"),
    ]
    filtered = filter_mandat_templates(templates, "Moyenne durée (MD - Bail mobilité)")
    assert {tpl.label for tpl in filtered} == {"mandat_md.docx", "Bail mobilité mandat.docx"}


def test_filter_cd_templates_prefers_cd_labels():
    templates = [
        _tpl("Mandat CD.docx"),
        _tpl("Mandat quelconque.docx"),
        _tpl("Bail Mobilité.docx"),
    ]
    filtered = filter_mandat_templates(templates, "Courte durée (CD)")
    assert {tpl.label for tpl in filtered} == {"Mandat CD.docx"}
