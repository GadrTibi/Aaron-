import os
import re
import streamlit as st

def _sanitize_filename(name: str, ext: str) -> str:
    base = os.path.basename(name)
    safe = re.sub(r"[^A-Za-z0-9 _\-.]", "_", base)
    if not safe.lower().endswith(f".{ext}"):
        safe += f".{ext}"
    return safe

@st.cache_data(ttl=5)
def list_templates(dirpath: str, ext: str):
    try:
        files = [f for f in os.listdir(dirpath) if f.lower().endswith(f".{ext}")]
        files.sort()
        return files
    except Exception:
        return []
