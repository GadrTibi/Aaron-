# MADE FOR YOU (MFY) — Document produit

> Point d'entrée produit canon. La spécification détaillée et **triangulée** vit dans
> [`../refonte/00-CDC-REFERENCE.md`](../refonte/00-CDC-REFERENCE.md) (source de vérité).
> Les points métier à confirmer : [`../refonte/02-points-ouverts-client.md`](../refonte/02-points-ouverts-client.md).

## En une phrase
Outil interne pour la conciergerie **MADE FOR YOU** : génère 3 documents commerciaux/contractuels
(**Estimation** de revenus PPTX, **Mandat** de gestion DOCX, **Book** d'accueil locataire PPTX/PDF)
en remplissant des **templates Office** à partir d'une saisie unique + enrichissement automatique
(quartier, transports, POI, images, carte, calculs de revenus).

## Utilisateur
Collaborateur MFY **non-développeur** → l'interface doit être simple, guidée et **utilisable en autonomie**
(y compris la configuration des clés API).

## Cible d'exécution
**Streamlit Community Cloud** (web) + exécution locale pour le dev. La piste `.exe`/PyInstaller est abandonnée.

## Régimes métier
- **CD** — courte durée / Airbnb touristique (avec graphique de saisonnalité).
- **MD** — moyenne durée / bail mobilité (loi ELAN, 1–10 mois, sans graphique).

## Invariants produit (ne jamais casser)
1. Données générales saisies **une seule fois**, partagées entre les 3 modules.
2. Tout champ enrichi automatiquement **reste modifiable** manuellement.
3. Les **3 scénarios** (pessimiste / cible / optimiste) sont visibles **dans l'UI**.
4. Bouton **« Rafraîchir les calculs »** qui ne relance pas les API externes.
5. **GenerationReport** + validation de template conservés (mode strict).
6. Les **templates Office = source de vérité visuelle** (l'app ne reconstruit jamais le design).

## Refonte en cours (2026-07)
Branche `refonte-propre`. Approche : **consolider l'existant** (le cœur métier est sain et testé),
supprimer le désordre, fiabiliser (calculs, tokens, POI), refondre l'UX (onglet clés API), finir le Book.
Plan : [`../refonte/01-PLAN-REFONTE.md`](../refonte/01-PLAN-REFONTE.md).
`main` = branche de déploiement Streamlit Cloud → **merge = décision PM**.
