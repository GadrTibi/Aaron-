import os
import sys
from streamlit.web import cli as stcli

if __name__ == "__main__":
    script = os.path.join(os.path.dirname(__file__), "app", "main.py")
    sys.argv = ["streamlit", "run", script, "--server.port", "8501"]
    sys.exit(stcli.main())
