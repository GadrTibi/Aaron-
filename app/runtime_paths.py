# app/runtime_paths.py
import os, sys, platform, pathlib

def _meipass_base() -> str:
    return getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))

def app_base_dir() -> str:
    return _meipass_base()

def user_root_dir() -> str:
    env = os.getenv("MFY_USER_DIR")
    if env:
        return env
    home = str(pathlib.Path.home())
    sysname = platform.system().lower()
    if "windows" in sysname or "darwin" in sysname:
        doc = os.path.join(home, "Documents")
        return os.path.join(doc, "MFY-App")
    return os.path.join(home, "MFY-App")

def ensure_dirs() -> dict:
    root = user_root_dir()
    templates = os.path.join(root, "templates")
    est = os.path.join(templates, "estimation")
    book = os.path.join(templates, "book")
    mandat = os.path.join(templates, "mandat")
    output = os.path.join(root, "output")
    cache_img = os.path.join(output, "_images_cache")

    for d in (root, templates, est, book, mandat, output, cache_img):
        os.makedirs(d, exist_ok=True)

    return {
        "USER_ROOT": root,
        "TPL_DIR": templates,
        "EST_TPL_DIR": est,
        "BOOK_TPL_DIR": book,
        "MANDAT_TPL_DIR": mandat,
        "OUT_DIR": output,
        "IMG_CACHE_DIR": cache_img,
    }
