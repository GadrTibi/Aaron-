"""Application launcher used when packaging with PyInstaller.

This module configures Streamlit entirely through environment variables so
that the executable runs in production mode without relying on CLI flags.
"""

import os
import sys


def resource_path(rel: str) -> str:
    """Return absolute path to a resource, compatible with PyInstaller."""

    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base, rel)


def main() -> None:
    """Configure Streamlit and launch the packaged app."""

    # Force Streamlit settings via environment variables (no CLI flags).
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHERUSAGESTATS"] = "false"

    # Port can be overridden via MFY_PORT, otherwise default to 8501.
    os.environ["STREAMLIT_SERVER_PORT"] = os.getenv("MFY_PORT", "8501")

    # Import Streamlit after environment variables are set.
    from streamlit.web.cli import main as st_main

    app_file = resource_path(os.path.join("app", "main.py"))

    # Start Streamlit with a minimal argv to avoid conflicts.
    sys.argv = ["streamlit", "run", app_file]
    st_main()


if __name__ == "__main__":
    main()
