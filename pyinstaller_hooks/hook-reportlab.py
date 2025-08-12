
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Ensure ReportLab's modules and data files (fonts, etc.) are bundled
hiddenimports = collect_submodules('reportlab')
datas = collect_data_files('reportlab')
