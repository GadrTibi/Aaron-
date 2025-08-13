#!/bin/zsh
set -e
rm -rf build dist mfy_app.spec
python3 -m pip install -r requirements.txt && python3 -m pip install pyinstaller reportlab
pyinstaller mfy_app.spec
open "dist/mfy_app/mfy_app.app"
# If Gatekeeper blocks the app:
# xattr -dr com.apple.quarantine "dist/mfy_app/mfy_app.app"
