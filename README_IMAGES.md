# Pipeline images lieux à visiter

Ce module gère la récupération d'images pour les lieux à visiter via une cascade de fournisseurs : Unsplash → Pexels → Wikimedia Commons. Chaque requête est journalisée dans `logs/images_debug.log` (horodatage, provider, POI, ville, pays, statut HTTP, message) afin de diagnostiquer rapidement les échecs.

## Variables d'environnement
- `UNSPLASH_ACCESS_KEY` (optionnelle) : clé d'API Unsplash. Sans cette clé, la cascade passe directement à Pexels/Wikimedia.
- `PEXELS_API_KEY` (optionnelle) : clé d'API Pexels. Sans cette clé, la cascade tombe sur Wikimedia.

## Commande de test
```bash
python tools/test_images.py "Tour Eiffel" --city Paris --country France
```
La commande affiche pour chaque provider l'URL appelée, le statut HTTP, l'image retenue, le chemin local final et la durée de la requête. Les mêmes informations sont ajoutées dans `logs/images_debug.log`.

## Log
Le fichier `logs/images_debug.log` est créé automatiquement (dossier `logs/`). Les niveaux INFO/WARNING/ERROR distinguent respectivement les requêtes normales, les retours d'erreur ou de fallback, et les échecs finaux avec bascule sur le placeholder `assets/no_image.png` (généré à la volée si absent).
