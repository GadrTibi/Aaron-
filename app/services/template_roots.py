from pathlib import Path


def _repo_root() -> Path:
    """
    Return the repository root (parent of the ``app`` package) based on the
    current file location. This avoids relying on the current working
    directory, which differs between local/dev and Streamlit Cloud.
    """
    return Path(__file__).resolve().parents[2]


REPO_TEMPLATE_ROOT = _repo_root() / "templates"
ESTIMATION_TPL_DIR = REPO_TEMPLATE_ROOT / "estimation"
MANDAT_TPL_DIR = REPO_TEMPLATE_ROOT / "mandat"
BOOK_TPL_DIR = REPO_TEMPLATE_ROOT / "book"
