# run_app.py
import os, sys
from streamlit.web.cli import main as st_main

def resource_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base, rel)

def main():
    app_file = resource_path(os.path.join("app", "main.py"))

    # === Fix Streamlit in packaged mode ===
    # Désactive le dev mode et passe la config via ENV (pas via flags CLI)
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHERUSAGESTATS"] = "false"

    # Port (optionnel). S'il est défini, on le passe via ENV, pas via --server.port
    port = os.getenv("MFY_PORT", "8501")
    os.environ["STREAMLIT_SERVER_PORT"] = port

    # Démarrage sans options en ligne de commande (évite les conflits)
    sys.argv = ["streamlit", "run", app_file]
    st_main()

if __name__ == "__main__":
    main()
