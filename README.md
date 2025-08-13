# MFY Local App (v2)

- Quartier : auto‑remplissage via boutons (Transports / Incontournables / Spots / Visites).
- Adresses du quartier — listes longues & sélection.
- Remplacement PPTX respectant **exactement** la mise en forme des tokens (même multi-runs).
- Recalcul revenus **en temps réel** (plus d'Excel).

Voir `app/main.py` pour les commentaires d'usage et `templates/*` pour déposer vos maquettes.

## Build a standalone Windows executable

From a PowerShell prompt at the project root:

```powershell
# Clean previous artifacts
Remove-Item -Recurse -Force build, dist, mfy_app.spec

# Create the executable
pyinstaller --noconfirm --clean --collect-all streamlit `
  --add-data "app;app" `
  --add-data "templates;templates" `
  --add-data "output;output" `
  --name mfy_app run_app.py
```

The binary is written to `dist/mfy_app/mfy_app.exe` and launches the Streamlit
application on port `8501` when executed.
