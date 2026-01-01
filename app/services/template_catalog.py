import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services import template_roots
from app.services.template_roots import list_estimation_templates

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
    if kind == "estimation":
        # Compat: retourne l'union CD/MD si appelé sans distinction de type.
        paths = list_estimation_templates("CD") + list_estimation_templates("MD")
        return sorted(paths, key=lambda p: p.name.lower())
    repo_dir = _kind_dir(kind)
    return _list_dir(repo_dir, ext)


def _to_items(paths: list[Path], source: TemplateSource) -> list[TemplateItem]:
    return [TemplateItem(label=p.name, source=source, path=p) for p in paths]


def list_repo_mandat_templates(mandat_type: str) -> list[TemplateItem]:
    """Liste les templates mandat dans le repo selon le type (CD/MD)."""

    repo_templates = template_roots.list_mandat_templates(mandat_type)
    if repo_templates:
        return _to_items(repo_templates, "repo")

    legacy_repo_templates = template_roots.list_legacy_mandat_templates()
    return _to_items(legacy_repo_templates, "repo")


def list_repo_estimation_templates(estimation_type: str) -> list[TemplateItem]:
    """Liste les templates estimation dans le repo selon le type (CD/MD)."""

    return _to_items(list_estimation_templates(estimation_type), "repo")


def list_env_templates(kind: str) -> list[TemplateItem]:
    """Liste les templates hérités (variables MFY_* ou dossiers locaux)."""

    ext = _KIND_EXT.get(kind)
    if not ext:
        raise ValueError(f"Type de template inconnu: {kind}")

    for legacy_dir in _iter_env_dirs(kind):
        legacy_templates = _list_dir(legacy_dir, ext)
        if legacy_templates:
            return _to_items(legacy_templates, "env")
    return []


def list_effective_mandat_templates(mandat_type: str) -> list[TemplateItem]:
    """
    Retourne les templates mandat disponibles pour un type donné en priorisant
    les dossiers versionnés du repo (templates/mandat/cd|md), puis les fichiers
    hérités (env ou templates/mandat/ racine pour compat).
    """

    repo_items = list_repo_mandat_templates(mandat_type)
    if repo_items:
        return repo_items
    return list_env_templates("mandat")


def _iter_estimation_env_dirs(estimation_type: str) -> list[Path]:
    subdir = "cd" if (estimation_type or "").strip().upper() == "CD" else "md"
    candidates: list[Path] = []
    for legacy_dir in _iter_env_dirs("estimation"):
        candidates.append(legacy_dir / subdir)
        candidates.append(legacy_dir / "estimation" / subdir)
        candidates.append(legacy_dir)
    return candidates


def list_env_estimation_templates(estimation_type: str) -> list[TemplateItem]:
    ext = _KIND_EXT.get("estimation")
    for env_dir in _iter_estimation_env_dirs(estimation_type):
        env_templates = _list_dir(env_dir, ext)
        if env_templates:
            return _to_items(env_templates, "env")
    return []


def list_effective_estimation_templates(estimation_type: str) -> list[TemplateItem]:
    """Priorise les templates Estimation du repo par type (CD/MD), sinon env."""

    repo_items = list_repo_estimation_templates(estimation_type)
    if repo_items:
        return repo_items
    return list_env_estimation_templates(estimation_type)


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
