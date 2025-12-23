## Résumé du produit
Outil Streamlit local permettant de générer trois livrables immobiliers : un PPTX d’estimation, un DOCX de mandat et un Book PPTX/PDF pour les locataires. L’app regroupe la saisie des données générales (propriétaire, bien), la découverte automatique du quartier (POI, transports, images), le calcul des revenus et l’injection des contenus dans des modèles Office en conservant la mise en forme. Les dépendances clés sont `streamlit`, `python-pptx`, `python-docx`, `requests`, `matplotlib` et `Pillow`. 【app/main.py†L1-L87】【app/views/estimation.py†L1-L88】

## Quickstart (local)
1. **Préparer l’environnement**
   - Python 3.12+ avec les dépendances `pip install -r requirements.txt`.
   - Clés facultatives (selon les fonctionnalités utilisées) : `GOOGLE_MAPS_API_KEY`, `UNSPLASH_ACCESS_KEY`, `PEXELS_API_KEY`, `GEOAPIFY_API_KEY`, `OPENTRIPMAP_API_KEY`.
2. **Option A : `run_app.py` (crée un espace utilisateur persistant)**
   ```bash
   python run_app.py            # ouvre Streamlit sur le port MFY_PORT (8501 par défaut)
   ```
   - Initialise `~/<Documents>/MFY-App` (ou `$MFY_USER_DIR`) avec `templates/estimation|book|mandat`, `output/` et `_images_cache/`, puis exporte les variables `MFY_*` pour pointer dessus. 【run_app.py†L1-L32】【app/runtime_paths.py†L6-L52】
3. **Option B : Streamlit direct (répertoire du repo)**
   ```bash
   streamlit run app/main.py --server.headless=true --global.developmentMode=false
   ```
   - Utilise les répertoires par défaut dans le repo (`app/templates/*` si présents, `output/`, `_images_cache/`). Surcharges possibles via `MFY_TPL_DIR`, `MFY_EST_TPL_DIR`, `MFY_BOOK_TPL_DIR`, `MFY_MAND_TPL_DIR`, `MFY_OUT_DIR`, `MFY_IMG_CACHE_DIR`. 【app/main.py†L12-L36】
4. **Arrêt rapide** : bouton “Quitter l’application” (sidebar) ou `Ctrl+C` dans le terminal.

## Pages Streamlit
- **Estimation** : collecte des données POI/visites, calcule revenus, génère le PPTX d’estimation avec graphique et images (POI + carte). 【app/views/estimation.py†L90-L320】
- **Mandat** : réutilise les données générales, ajoute les champs mandat et génère le DOCX. 【app/views/mandat.py†L17-L89】
- **Book** : guide d’accès locataire (transports, instructions d’accès, Wi‑Fi, photos d’accès, carte) puis génère PPTX ou PDF léger. 【app/views/book.py†L1-L165】
- **Paramètres / Clés API** : saisie persistante de `GOOGLE_MAPS_API_KEY` via `~/.mfy_local_app/secrets.toml` ou récupération depuis l’environnement/`st.secrets`. 【app/views/settings_keys.py†L1-L85】

## Flux de bout en bout
- **Estimation → PPTX**
  1. L’utilisateur saisit adresse, caractéristiques, prix nuitée et rayon (UI).
  2. Géocodage Nominatim (`geocode_address`) stocke lat/lon. 【app/services/geocode.py†L20-L51】
  3. Transports : `TransportService` agrège GTFS/OSM/Google pour taxis/métro/bus, stocke dans `session_state`. 【services/transports_v3.py†L1-L215】
  4. POI : `GooglePlacesService` charge incontournables/spots/visites (cache 120 s). 【app/views/estimation.py†L15-L61】
  5. Images visites : `WikiImageService.candidates` + téléchargement ou upload utilisateur. 【app/views/estimation.py†L122-L230】
  6. Carte statique : `build_static_map` (OSM staticmap). 【app/services/map_image.py†L1-L26】
  7. Graphique prix : `build_estimation_histo` génère `out/plots/estimation_histo.png`. 【app/services/plots.py†L49-L117】
  8. Mapping tokens + images → `generate_estimation_pptx` (remplacement texte + images/mask + histogramme) écrit dans `OUT_DIR/Estimation - <adresse>.pptx`. 【app/services/pptx_fill.py†L90-L170】【app/views/estimation.py†L246-L320】
- **Mandat → DOCX**
  1. L’utilisateur sélectionne un modèle DOCX.
  2. `build_mandat_mapping` assemble les données générales + champs spécifiques mandat (dates, destination, commission, pièces, animaux…). 【app/services/mandat_tokens.py†L1-L107】
  3. `generate_docx_from_template` remplace les tokens et signale ceux restants (stdout), puis écrit `OUT_DIR/Mandat - <adresse>.docx`. 【app/services/docx_fill.py†L39-L83】【app/views/mandat.py†L53-L89】
- **Book → PPTX/PDF (incomplet)**
  1. Adresse + transports (Overpass via `fetch_transports`, `list_metro_lines`, `list_bus_lines`) ou import depuis l’état Estimation. 【app/services/poi.py†L1-L165】
  2. Instructions d’accès + photos (upload) + Wi‑Fi.
  3. Carte statique (`build_static_map`) et images accès injectées dans `generate_book_pptx`. PDF alternatif généré par `build_book_pdf` (sections vides par défaut). 【app/services/pptx_fill.py†L172-L226】【app/services/book_pdf.py†L1-L33】

## Templates attendus
- PPTX Estimation : tous les fichiers dans `EST_TPL_DIR` (upload possible via UI) ou héritage `estimation_template.pptx` dans `TPL_DIR`. 【app/views/estimation.py†L96-L121】
- DOCX Mandat : modèles dans `MANDAT_TPL_DIR` ou `mandat_template.docx` dans `TPL_DIR`. 【app/views/mandat.py†L17-L47】
- PPTX Book : modèles dans `BOOK_TPL_DIR` (UI upload). Aucun héritage. 【app/views/book.py†L22-L52】

## Gestion des chemins
- **Création automatique** : `TPL_DIR`, `EST_TPL_DIR`, `BOOK_TPL_DIR`, `MANDAT_TPL_DIR`, `OUT_DIR`, `IMG_CACHE_DIR` créés au démarrage. Par défaut dans le repo (`app/main.py`) ou dans `~/Documents/MFY-App` via `run_app.py`/`runtime_paths.ensure_dirs`. 【app/main.py†L28-L45】【app/runtime_paths.py†L19-L52】
- **Outputs** : `OUT_DIR` pour PPTX/DOCX/PDF, `out/plots` pour graphiques, `out/images/visits|poi` pour photos, `_images_cache` pour téléchargements POI.
- **Caches** : `out/cache/places` (Geoapify/OpenTripMap), `out/cache/wiki` (Wikimedia), `IMG_CACHE_DIR` pour images POI téléchargeables.
- **Logs** : `logs/images_debug.log` (image_fetcher pipeline, auto-créé). 【app/services/image_fetcher.py†L15-L36】
- **Secrets** : `~/.mfy_local_app/secrets.toml` (créé/écrit par UI) ou `.streamlit/secrets.toml` (lecture seule).

## Gestion des secrets / clés (priorité)
1. Variables d’environnement (toutes les clés). 【app/views/settings_keys.py†L33-L55】
2. `st.secrets` (si Streamlit fournit un `secrets.toml` dans le projet).
3. Fichiers `secrets.toml` aux emplacements : `~/.mfy_local_app/secrets.toml`, `.streamlit/secrets.toml`, `app/.streamlit/secrets.toml`. 【app/views/settings_keys.py†L17-L55】
4. UI “Paramètres / Clés API” écrit dans `~/.mfy_local_app/secrets.toml`.
5. Pour certains services : fallback à valeurs vides → fonctionnalités limitées (ex. Google Places/Unsplash/Pexels). 【services/places_google.py†L6-L25】【app/services/image_fetcher.py†L85-L142】

## Stratégie de cache
- **Streamlit** : `@st.cache_data` sur `list_templates` (TTL 5 s) et `_load_google_places` (TTL 120 s). 【app/views/utils.py†L9-L21】【app/views/estimation.py†L15-L31】
- **Disque** : 
  - Geoapify/OpenTripMap via `config.places_settings` (JSON sous `out/cache/places`, TTL 48 h par service). 【config/places_settings.py†L1-L61】
  - Wikimedia/Wikidata via `services.cache_utils` (JSON sous `out/cache/wiki`, TTL contrôlé par appelant). 【services/cache_utils.py†L1-L39】
  - Images POI téléchargées sous `IMG_CACHE_DIR` / `out/images/*` pour réutilisation manuelle.
- **Invalidation** : TTL + écrasement. Pas de purge automatique des outputs.

## Points d’extension
- **Nouveaux providers images POI** : étendre `_provider_chain()` dans `app/services/image_fetcher.py` et gérer les clés d’API/headers/timeouts. Le log centralisé `logs/images_debug.log` facilite le diagnostic. 【app/services/image_fetcher.py†L180-L229】
- **POI/Transports** : ajouter un provider dans `TransportService` (ordre `provider_order`) ou brancher un autre service dans `GooglePlacesService`/`GeoapifyPlacesService`. Respecter la normalisation `_normalize_lines` pour limiter les doublons. 【services/transports_v3.py†L157-L215】
- **Templates & tokens** : ajouter des mappings dans `build_mandat_mapping` ou `build_book_mapping` et définir les shapes/tags attendus pour les images dans `pptx_fill.py`/`pptx_images.py`. 【app/services/pptx_fill.py†L120-L170】
