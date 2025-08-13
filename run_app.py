import os
import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """Resolve path to bundled resources inside PyInstaller executables."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def main() -> None:
    app_file = resource_path("app/main.py")

    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENTMODE", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHERUSAGESTATS", "false")
    port = os.environ.get("MFY_PORT", "8501")
    os.environ.setdefault("STREAMLIT_SERVER_PORT", port)

    sys.argv = ["streamlit", "run", str(app_file)]
    from streamlit.web.cli import main as st_main
    st_main()


if __name__ == "__main__":
    main()
