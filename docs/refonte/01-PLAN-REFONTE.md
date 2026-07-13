# Plan de refonte MFY — 2026-07

**Décision d'approche** (technique, prise par le Tech Lead) : **refonte sur l'existant**, pas
rewrite from scratch. Justification : le cœur métier (calculs, remplacement de tokens,
GenerationReport, validation, tests) est **sain et testé** (111/114 tests verts) ; le doc de
transmission le confirme (§8.7). On **garde les briques prouvées**, on **supprime le désordre**,
on **fiabilise** et on **embellit**.

**Branche** : `refonte-propre`. `main` = branche de déploiement Streamlit Cloud → **merge = décision PM** (irréversible).

**Cible** : Streamlit Cloud-first (web) + local dev. Abandon `.exe`/PyInstaller.

---

## Lots (ordre d'exécution)

### Lot A — Nettoyage & architecture
- Inventorier + supprimer le **code mort / modules jamais importés / providers pas utilisés**.
- Unifier la **double couche services** (`app/services/` + `services/`) → une seule.
- Retirer la piste **PyInstaller/.exe** (code, docs, branches obsolètes).
- Corriger le **bug cache Windows** (`:` illégal dans nom de fichier → séparateur sûr).
- Sortie : arbo claire, imports cohérents, tests toujours verts.

### Lot B — Calculs (fiabilité métier)
- **Une règle d'arrondi unique** reproduisant EXACTEMENT les 2 jeux de référence (CD 179/85 %, MD 126/26).
- Corriger le test MD cassé (`days_per_month=26`).
- Purger tout résidu de logique morte (ménage déjà OK).
- Tests de recette CD + MD **verts et gelés**.

### Lot C — Tokens & POI
- **Remplacement multi-runs robuste** PPTX + DOCX (préfixe/suffixe préservés, tokens splittés gérés).
- Respect **strict du rayon** pour spots/visites (Haversine, jamais de hors-rayon).
- Règle **devise** (pas de double €).
- Tests : substitution en contexte (préfixe+token+suffixe), filtrage rayon.

### Lot D — UX / Interface
- **Onglet Clés API repensé** : tous les providers, saisie masquée, bouton **Tester** (pastille 🟢/🔴),
  **statut**, lien « où obtenir », **rerun auto** après enregistrement, distinction essentiel/optionnel.
- **Onboarding** 1re utilisation + **indicateur de disponibilité** en tête d'app.
- **3 scénarios visibles** dans l'UI + **bouton « Rafraîchir les calculs »** (sans re-appeler les API).
- Nettoyage `session_state` (pattern pending + `st.rerun()`), ergonomie générale.

### Lot E — Book
- Finaliser tokens/carte/PDF/validation au niveau atteignable sans nouvelles specs client.

### Gate qualité (chaque lot)
- Suite de tests verte (périmètre nommé).
- Passage **Akainu** (adversarial) avant de déclarer un lot « fait ».
- Commit par lot ; **pas** de merge `main` sans GO PM.

---

## Points ouverts (n'empêchent pas de builder)
Cf. `02-points-ouverts-client.md`. On reproduit les jeux de référence client et on documente les
hypothèses ; confirmation client requise avant recette finale.
