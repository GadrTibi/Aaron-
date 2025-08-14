# run_app.py (extrait)
import os, sys, webbrowser
from streamlit.web.cli import main as st_main
from app.runtime_paths import ensure_dirs

def main():
    cfg = ensure_dirs()
    os.environ["MFY_TPL_DIR"]       = cfg["TPL_DIR"]
    os.environ["MFY_EST_TPL_DIR"]   = cfg["EST_TPL_DIR"]
    os.environ["MFY_BOOK_TPL_DIR"]  = cfg["BOOK_TPL_DIR"]
    os.environ["MFY_MAND_TPL_DIR"]  = cfg["MANDAT_TPL_DIR"]
    os.environ["MFY_OUT_DIR"]       = cfg["OUT_DIR"]
    os.environ["MFY_IMG_CACHE_DIR"] = cfg["IMG_CACHE_DIR"]

    # Désactive explicitement le dev mode pour autoriser server.port
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    app_path = os.path.join(os.path.dirname(__file__), "app", "main.py")
    port = os.getenv("MFY_PORT", "8501")

    sys.argv = [
        "streamlit", "run", app_path,
        "--global.developmentMode=false",       # <= clé !
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
        f"--server.port={port}",
    ]

    try:
        webbrowser.open_new_tab(f"http://localhost:{port}")
    except Exception:
        pass

    st_main()

if __name__ == "__main__":
    main()
