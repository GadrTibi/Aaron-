import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services import template_roots

TemplateSource = Literal["repo", "env"]


@dataclass(frozen=True)
class TemplateItem:
    label: str
    source: TemplateSource
    path: Path


_KIND_EXT = {
    "estimation": ".pptx",
    "mandat": ".docx",
    "book": ".pptx",
}


def _kind_dir(kind: str) -> Path:
    if kind not in _KIND_EXT:
        raise ValueError(f"Type de template inconnu: {kind}")
    if kind == "estimation":
        return template_roots.ESTIMATION_TPL_DIR
    if kind == "mandat":
        return template_roots.MANDAT_TPL_DIR
    return template_roots.BOOK_TPL_DIR


def _iter_env_dirs(kind: str) -> list[Path]:
    """
    Retourne les répertoires hérités (variables d'environnement MFY_* ou defaults
    historiques dans app/main.py) pour compat local.
    """
    env_map = {
        "estimation": os.getenv("MFY_EST_TPL_DIR"),
        "mandat": os.getenv("MFY_MAND_TPL_DIR"),
        "book": os.getenv("MFY_BOOK_TPL_DIR"),
    }
    env_root = os.getenv("MFY_TPL_DIR")
    app_root = Path(__file__).resolve().parents[1]
    default_root = Path(env_root) if env_root else app_root / "templates"

    fallbacks = []
    env_dir = env_map.get(kind)
    if env_dir:
        fallbacks.append(Path(env_dir))
    subdir = "estimation" if kind == "estimation" else ("mandat" if kind == "mandat" else "book")
    fallbacks.append(default_root / subdir)
    fallbacks.append(default_root)
    return fallbacks


def _list_dir(dirpath: Path, ext: str) -> list[Path]:
    dirpath.mkdir(parents=True, exist_ok=True)
    if not dirpath.exists() or not dirpath.is_dir():
        return []
    files = [p for p in dirpath.iterdir() if p.is_file() and p.suffix.lower() == ext]
    return sorted(files, key=lambda p: p.name.lower())


def list_repo_templates(kind: str) -> list[Path]:
    """Liste les templates embarqués dans le repo Git pour le type demandé."""
    ext = _KIND_EXT.get(kind)
    if not ext:
        raise ValueError(f"Type de template inconnu: {kind}")
    repo_dir = _kind_dir(kind)
    return _list_dir(repo_dir, ext)


def list_effective_templates(kind: str) -> list[TemplateItem]:
    """
    Retourne les templates utilisables, en priorisant ceux du repo Git. Si aucun
    template n'est trouvé dans ``templates/<kind>``, on bascule sur les
    répertoires hérités (MFY_* ou defaults locaux).
    """
    ext = _KIND_EXT.get(kind)
    if not ext:
        raise ValueError(f"Type de template inconnu: {kind}")

    repo_templates = list_repo_templates(kind)
    if repo_templates:
        return [TemplateItem(label=p.name, source="repo", path=p) for p in repo_templates]

    for legacy_dir in _iter_env_dirs(kind):
        legacy_templates = _list_dir(legacy_dir, ext)
        if legacy_templates:
            return [TemplateItem(label=p.name, source="env", path=p) for p in legacy_templates]

    return []
