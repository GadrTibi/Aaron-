import os
import sys
from streamlit.web import bootstrap


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller bundles."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base_path, relative_path)


if __name__ == "__main__":
    script = resource_path(os.path.join("app", "main.py"))
    bootstrap.run(script, "", [], {})
