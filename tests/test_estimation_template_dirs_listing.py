from pathlib import Path

from app.services import template_roots


def test_list_estimation_templates_by_type(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    cd_dir = repo_root / "templates" / "estimation" / "cd"
    md_dir = repo_root / "templates" / "estimation" / "md"
    cd_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    cd_tpl = cd_dir / "a.pptx"
    md_tpl = md_dir / "b.pptx"
    cd_tpl.touch()
    md_tpl.touch()

    monkeypatch.setattr(template_roots, "REPO_TPL_ROOT", repo_root / "templates")
    monkeypatch.setattr(template_roots, "ESTIMATION_TPL_DIR", repo_root / "templates" / "estimation")
    monkeypatch.setattr(template_roots, "ESTIMATION_CD_TPL_DIR", cd_dir)
    monkeypatch.setattr(template_roots, "ESTIMATION_MD_TPL_DIR", md_dir)

    cd_list = template_roots.list_estimation_templates("CD")
    md_list = template_roots.list_estimation_templates("MD")

    assert cd_list == [cd_tpl]
    assert md_list == [md_tpl]
