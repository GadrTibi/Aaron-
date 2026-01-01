from pathlib import Path

from app.services import template_roots, template_catalog


def test_list_repo_templates_returns_sorted_filtered(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    est_dir_cd = repo_root / "templates" / "estimation" / "cd"
    est_dir_cd.mkdir(parents=True, exist_ok=True)
    (est_dir_cd / "z-template.pptx").touch()
    (est_dir_cd / "a-template.PPTX").touch()
    (est_dir_cd / "ignore.txt").touch()

    monkeypatch.setattr(template_roots, "REPO_TEMPLATE_ROOT", repo_root / "templates")
    monkeypatch.setattr(template_roots, "ESTIMATION_TPL_DIR", repo_root / "templates" / "estimation")
    monkeypatch.setattr(template_roots, "ESTIMATION_CD_TPL_DIR", est_dir_cd)
    monkeypatch.setattr(template_roots, "ESTIMATION_MD_TPL_DIR", repo_root / "templates" / "estimation" / "md")
    monkeypatch.setattr(template_roots, "MANDAT_TPL_DIR", repo_root / "templates" / "mandat")
    monkeypatch.setattr(template_roots, "BOOK_TPL_DIR", repo_root / "templates" / "book")

    templates = template_catalog.list_repo_templates("estimation")

    assert [tpl.name for tpl in templates] == ["a-template.PPTX", "z-template.pptx"]
