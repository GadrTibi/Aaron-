# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path

block_cipher = None

packages = [
    "streamlit",
    "pptx",
    "docx",
    "lxml",
    "PIL",
    "staticmap",
    "reportlab",
]

datas, binaries, hiddenimports = [], [], []
for pkg in packages:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

root = Path(__file__).parent

# Add project directories with filtering
EXCLUDES = {"Thumbs.db", ".DS_Store"}
SUFFIX_EXCLUDES = {".tmp", ".lock"}

for folder in ["app", "templates", "output"]:
    folder_path = root / folder
    if folder_path.exists():
        for file in folder_path.rglob('*'):
            if file.is_file() and not (
                file.name.startswith('~$') or
                file.name in EXCLUDES or
                file.suffix in SUFFIX_EXCLUDES
            ):
                datas.append((str(file), str(file.relative_to(root))))


a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='mfy_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # set to True for diagnostics
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='mfy_app',
)
