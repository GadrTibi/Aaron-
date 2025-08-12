from PyInstaller.utils.hooks import collect_data_files

# Include Streamlit's static assets (index.html, JS, etc.)
datas = collect_data_files('streamlit', include_py_files=False)
