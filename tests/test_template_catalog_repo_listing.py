from pathlib import Path

from app.services import template_roots, template_catalog


def test_list_repo_templates_returns_sorted_filtered(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    est_dir = repo_root / "templates" / "estimation"
    est_dir.mkdir(parents=True, exist_ok=True)
    (est_dir / "z-template.pptx").touch()
    (est_dir / "a-template.PPTX").touch()
    (est_dir / "ignore.txt").touch()

    monkeypatch.setattr(template_roots, "REPO_TEMPLATE_ROOT", repo_root / "templates")
    monkeypatch.setattr(template_roots, "ESTIMATION_TPL_DIR", est_dir)
    monkeypatch.setattr(template_roots, "MANDAT_TPL_DIR", repo_root / "templates" / "mandat")
    monkeypatch.setattr(template_roots, "BOOK_TPL_DIR", repo_root / "templates" / "book")

    templates = template_catalog.list_repo_templates("estimation")

    assert [tpl.name for tpl in templates] == ["a-template.PPTX", "z-template.pptx"]
