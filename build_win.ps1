# Build Windows executable
try { taskkill /IM mfy_app.exe /F 2>$null } catch { }
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

pip install -r requirements.txt
pip install pyinstaller reportlab

pyinstaller mfy_app.spec

Write-Host 'cd .\dist\mfy_app'
Write-Host '$env:MFY_PORT="8501"; .\mfy_app.exe'
