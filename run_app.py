import sys
from pathlib import Path
from streamlit.web import cli as stcli

if __name__ == "__main__":
    # When packaged with PyInstaller, the application is extracted to a
    # temporary directory referenced by ``sys._MEIPASS``.  Use it as the base
    # directory; otherwise fall back to the location of this file.
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    script = base_dir / "app" / "main.py"
    sys.argv = ["streamlit", "run", str(script), "--server.port", "8501"]
    sys.exit(stcli.main())
