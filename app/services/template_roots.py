from pathlib import Path


def _repo_root() -> Path:
    """
    Return the repository root (parent of the ``app`` package) based on the
    current file location. This avoids relying on the current working
    directory, which differs between local/dev and Streamlit Cloud.
    """
    return Path(__file__).resolve().parents[2]


REPO_TPL_ROOT = _repo_root() / "templates"
REPO_TEMPLATE_ROOT = REPO_TPL_ROOT  # Compat
ESTIMATION_TPL_DIR = REPO_TPL_ROOT / "estimation"
MANDAT_TPL_DIR = REPO_TPL_ROOT / "mandat"
MANDAT_CD_TPL_DIR = MANDAT_TPL_DIR / "cd"
MANDAT_MD_TPL_DIR = MANDAT_TPL_DIR / "md"
BOOK_TPL_DIR = REPO_TPL_ROOT / "book"


def get_mandat_templates_dir(mandat_type: str) -> Path:
    mandat_key = (mandat_type or "").strip().upper()
    if mandat_key == "MD":
        return MANDAT_MD_TPL_DIR
    if mandat_key == "CD":
        return MANDAT_CD_TPL_DIR
    raise ValueError(f"Type de mandat inconnu: {mandat_type}")


def list_mandat_templates(mandat_type: str) -> list[Path]:
    target_dir = get_mandat_templates_dir(mandat_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    if not target_dir.exists() or not target_dir.is_dir():
        return []
    files = [p for p in target_dir.iterdir() if p.is_file() and p.suffix.lower() == ".docx"]
    return sorted(files, key=lambda p: p.name.lower())


def list_legacy_mandat_templates() -> list[Path]:
    """Templates DOCX situés directement sous templates/mandat (compat héritée)."""

    if not MANDAT_TPL_DIR.exists() or not MANDAT_TPL_DIR.is_dir():
        return []
    files = [p for p in MANDAT_TPL_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".docx"]
    return sorted(files, key=lambda p: p.name.lower())
