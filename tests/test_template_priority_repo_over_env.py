from pathlib import Path

import pytest

from app.services import template_roots, template_catalog


@pytest.mark.parametrize("kind, ext", [("estimation", ".pptx"), ("mandat", ".docx"), ("book", ".pptx")])
def test_repo_templates_have_priority_over_env(monkeypatch, tmp_path, kind, ext):
    repo_root = tmp_path / "repo"
    repo_dir = repo_root / "templates" / kind
    repo_dir.mkdir(parents=True, exist_ok=True)
    repo_tpl = repo_dir / f"repo_{kind}{ext}"
    repo_tpl.touch()

    legacy_dir = tmp_path / "legacy" / kind
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / f"legacy_{kind}{ext}").touch()

    env_var = {
        "estimation": "MFY_EST_TPL_DIR",
        "mandat": "MFY_MAND_TPL_DIR",
        "book": "MFY_BOOK_TPL_DIR",
    }[kind]
    monkeypatch.setenv(env_var, str(legacy_dir))

    monkeypatch.setattr(template_roots, "REPO_TEMPLATE_ROOT", repo_root / "templates")
    monkeypatch.setattr(template_roots, "ESTIMATION_TPL_DIR", repo_root / "templates" / "estimation")
    monkeypatch.setattr(template_roots, "MANDAT_TPL_DIR", repo_root / "templates" / "mandat")
    monkeypatch.setattr(template_roots, "BOOK_TPL_DIR", repo_root / "templates" / "book")

    templates = template_catalog.list_effective_templates(kind)

    assert len(templates) == 1
    assert templates[0].path == repo_tpl
    assert templates[0].source == "repo"
