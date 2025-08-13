from PyInstaller.utils.hooks import collect_data_files

# Include only Streamlit's static assets (HTML/JS/CSS) so the app can serve
# its frontend when packaged with PyInstaller.
datas = collect_data_files(
    "streamlit", includes=["static/*", "static/**/*"], include_py_files=False
)

# Ensure dynamic Streamlit modules are bundled
hiddenimports = ["streamlit.runtime.scriptrunner.magic_funcs"]
