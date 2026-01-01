from pathlib import Path

from app.services import template_roots, template_catalog


def _wire_repo(monkeypatch, repo_root: Path) -> None:
    monkeypatch.setattr(template_roots, "REPO_TPL_ROOT", repo_root / "templates")
    monkeypatch.setattr(template_roots, "REPO_TEMPLATE_ROOT", repo_root / "templates")
    monkeypatch.setattr(template_roots, "MANDAT_TPL_DIR", repo_root / "templates" / "mandat")
    monkeypatch.setattr(template_roots, "MANDAT_CD_TPL_DIR", repo_root / "templates" / "mandat" / "cd")
    monkeypatch.setattr(template_roots, "MANDAT_MD_TPL_DIR", repo_root / "templates" / "mandat" / "md")


def test_list_mandat_templates_by_dir(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    cd_dir = repo_root / "templates" / "mandat" / "cd"
    md_dir = repo_root / "templates" / "mandat" / "md"
    cd_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    (cd_dir / "a_cd.docx").touch()
    (md_dir / "b_md.docx").touch()

    _wire_repo(monkeypatch, repo_root)

    templates_cd = template_roots.list_mandat_templates("CD")
    templates_md = template_roots.list_mandat_templates("MD")

    assert [tpl.name for tpl in templates_cd] == ["a_cd.docx"]
    assert [tpl.name for tpl in templates_md] == ["b_md.docx"]

    repo_cd_items = template_catalog.list_repo_mandat_templates("CD")
    repo_md_items = template_catalog.list_repo_mandat_templates("MD")

    assert [tpl.label for tpl in repo_cd_items] == ["a_cd.docx"]
    assert [tpl.label for tpl in repo_md_items] == ["b_md.docx"]
