# Cahier des charges de référence — MADE FOR YOU (MFY)

> **Statut** : source de vérité de la refonte 2026-07. Consolidé et **triangulé**
> (code + templates + tests + doc de transmission ChatGPT). Chaque règle porte un
> niveau de confiance. Ne jamais coder un point ⚠️/❓ sans vérifier ou faire confirmer.
>
> **Sources** : `sources/CDC-metier-chatgpt.md` (intention métier), code sur `main`,
> templates Office versionnés, suite de tests. Le **code + les templates + les chiffres
> de référence client** priment sur la narration ChatGPT en cas de conflit.

Légende de confiance :
- ✅ **CONFIRMÉ** — concordance code + test/template (fiable).
- ⚠️ **À VÉRIFIER** — affirmé par une seule source, ou divergence mineure.
- ❓ **POINT OUVERT MÉTIER** — à confirmer avec le client MFY avant figement définitif.

---

## 1. Vision & acteurs

**MFY** est une conciergerie immobilière (location Airbnb / gestion locative). L'outil
génère **3 documents commerciaux/contractuels** à partir de **templates Office** (le design
reste dans PowerPoint/Word ; l'app ne fait que remplir des *tokens* sans altérer la mise
en forme). Objectif : **saisir une fois**, enrichir automatiquement (quartier, transports,
POI, images, carte, calculs), produire un document **directement présentable au client**.

| Acteur | Rôle |
|---|---|
| **Collaborateur MFY** | Utilisateur de l'app. **Non-développeur** → l'UI doit être simple, guidée, autonome. |
| Propriétaire | Destinataire de l'**Estimation** et signataire du **Mandat**. |
| Locataire | Destinataire du **Book** d'accueil. |

**Cible d'exécution** ✅ : **Streamlit Community Cloud** (web) — la piste `.exe`/PyInstaller
est **abandonnée**. Exécution locale conservée pour le dev. Templates persistants via **Git**.
Secrets : locaux en dev (`~/.mfy_local_app/secrets.toml`), `st.secrets` en cloud.

---

## 2. Les 3 modules

### 2.1 Estimation (PPTX) — le plus abouti
Document de prospection : présente le logement, le quartier, le potentiel, les **revenus**
estimés et la valeur ajoutée MFY. Deux régimes :
- **CD** (courte durée / Airbnb touristique) : graphique de saisonnalité, calcul prix-nuitée × occupation.
- **MD** (moyenne durée / bail mobilité, loi ELAN, 1–10 mois) : **pas** de graphique, calcul prix × jours/mois.

Un **seul onglet** avec **switch CD/MD** ✅ ; dossiers de templates séparés (`templates/estimation/cd|md/`).

**Contenu obligatoire** : logement (pièces, SDB, couchages, surface, points forts, challenges) ·
quartier (adresse, intro attractive, transports, incontournables, spots, visites) · revenus
(taux occ., jours, prix nuitée, brut, frais plateforme, commission MFY, frais généraux,
pessimiste/cible/optimiste).

**Règles rédactionnelles** ✅ (concordent code+templates) :
- L'intro quartier commence par le **nom du quartier/arrondissement**, jamais par l'adresse complète.
- Transports au **format compact** (ex. `Métro, ligne 2, 12` / `Bus, ligne 30, 40, 54`), sans laïus marketing.
- **Rayon POI par défaut = 300 m** ✅ (`DEFAULT_RADIUS_M = 300`). Spots & visites **strictement dans le rayon** ; ne jamais compléter avec un hors-rayon.

### 2.2 Mandat (DOCX)
Document juridique. L'app **remplit sans modifier** le contenu juridique ni la présentation.
Switch **CD/MD**, filtrage **par dossier** (`templates/mandat/cd|md/`), pas par nom de fichier ✅.

**1re question obligatoire : Personne physique / Personne morale** ✅ (doc + test `test_mandat_owner_type_mapping`).
Réutilisation des **mêmes tokens** pour la personne morale (aucun nouveau token Word) :

| Champ UI (morale) | Token DOCX réutilisé |
|---|---|
| Raison sociale | `«Nom_du_propriétaire»` |
| Nom de la société | `«Prénom_du_propriétaire»` |
| Adresse de domiciliation | `«Adresse_du_propriétaire»` |

MD ajoute 2 tokens de signature : `«MANDAT_JOUR_SIGNATURE»`, `«MANDAT_DATE_SIGNATURE»` ✅ (présents dans le template MD réel). CD : compléter la phrase « Fait à Paris, le … » ⚠️ (à vérifier sur template CD).

### 2.3 Book (PPTX/PDF) — **incomplet**
Guide d'accueil locataire : adresse, transports, carte, instructions d'accès, photos, Wi-Fi, consignes.
Génération PPTX + PDF léger. ❓ **Le moins finalisé** : pas de validation métier/tokens/PDF équivalente aux 2 autres. À finir dans le Lot E, au niveau de fidélité atteignable sans nouvelles specs client.

---

## 3. Règles de calcul (le cœur — triangulé)

Frais de ménage : **supprimés partout** ✅ (0 résidu dans code, config, templates).

**Frais plateforme** ✅ = `revenu_brut × pct_plateforme` (pct modifiable).
**Commission MFY** ✅ = `(revenu_brut − frais_plateforme) × pct_mfy` (sur le net après plateforme).
**Frais généraux** ✅ = `frais_plateforme + commission_mfy`.
**Base estimation / revenu net** ✅ = `revenu_brut − frais_plateforme − commission_mfy`.
Les 3 scénarios partent de cette base (ne jamais re-soustraire les frais généraux).

### 3.1 CD
`revenu_brut = prix_nuitée × (taux_occ/100) × 30,46` ✅ (code+test concordent).
Jours **affichés** = `floor(taux_occ/100 × 30)` (30, pas 30,46 — incohérence assumée, calibrage sur visuel client).
Scénarios ✅ : pessimiste **0,88** / cible **1,00** / optimiste **1,15**, arrondi **au 50 le plus proche**.
❓ **Justification métier du 30,46 non fournie** → à confirmer client (cf. `02-points-ouverts-client.md`).

**Jeu de référence CD** ✅ (test de recette permanent) : prix 179 €, occ 85 %, plateforme 15 %, MFY 15 %
→ brut **4 634 €**, plateforme **695 €**, commission **591 €**, frais **1 286 €**, pess **2 950 €**, cible **3 350 €**, opt **3 850 €**.

### 3.2 MD
`revenu_brut = prix_nuitée × jours_par_mois` ✅ (les **jours** pilotent le revenu ; le **taux** est affiché mais ne re-multiplie pas).
Défauts : taux **83 %**, jours **26**. Scénarios ✅ : pessimiste **0,93** / cible **1,00** / optimiste **1,06**, arrondi **au 50 inférieur** (`floor(x/50)×50`).

**Jeu de référence MD** (rapporté par le doc de transmission) : prix 126 €, jours 26, taux 83 %, plateforme 15 %, MFY 15 %
→ brut **3 276 €** ✅, commission **418 €** ✅, pess **2 200 €** ✅, cible **2 350 €** ✅, opt **2 500 €** ✅ ;
plateforme **492 €** ⚠️ et frais **910 €** ⚠️ (voir divergence ci-dessous).

⚠️ **Divergence d'arrondi NON RÉSOLUE (point ouvert P3)** : `3276 × 15 % = 491,4` → le code fait
`round()` = **491 €** (frais **909 €**), alors que le doc de transmission **rapporte 492 € / 910 €**.
**Constat mathématique** : 491,4 s'arrondit à 491 par tout arrondi standard ; **492 est inatteignable
par la même règle que celle qui reproduit le jeu CD** (CD exige `round(695,1)=695` ; un `ceil` donnerait
696 et casserait CD). Donc 492/910 suppose soit une **règle d'arrondi MD spécifique côté client**, soit
une **imprécision du report** — **on ne peut pas trancher sans le screenshot client réel**. En attendant,
le code et les tests figent **491/909** (comportement `round()` cohérent avec CD) ; **ne pas préjuger**
que 492 est faux. À confirmer avec MFY (P3). Le test `test_md_matches_client_numbers` était par ailleurs
cassé (il omettait `days_per_month=26`) — corrigé au Lot B.

---

## 4. Sources de données externes (triangulé)

Ordre de résolution des clés ✅ : env → `st.secrets` → `~/.mfy_local_app/secrets.toml` → `.streamlit/secrets.toml`.

| Service | Rôle | Statut | Clé |
|---|---|---|---|
| **Nominatim** | Géocodage adresse→lat/lon | Essentiel, fallback possible | non (UA obligatoire ✅ présent) |
| **Google Places** | POI / incontournables / géocodage secours | Important, mode dégradé si absent | `GOOGLE_MAPS_API_KEY` |
| **OpenAI** | Génère intro quartier + transports compacts (JSON) | Important (présentable, rapide) | `OPENAI_API_KEY` |
| Geoapify | Fallback POI / géocodage | Optionnel | `GEOAPIFY_API_KEY` |
| OpenTripMap | POI touristiques (fallback) | Optionnel | `OPENTRIPMAP_API_KEY` |
| Wikimedia/Wikidata | POI connus + images | Fallback, sans clé | non |

> Unsplash / Pexels : **retirés** (2026-07). Leur seul consommateur (`image_fetcher.py`) a été
> supprimé au Lot A ; les images de lieux passent désormais par Wikimedia + upload manuel.

**Overpass / GTFS** : ⚠️ **rétrogradés** — lents, instables, résultats non présentables (confond nom d'arrêt et n° de ligne). Ne doivent **plus** être le cœur de « Quartier & Transports » (remplacés par OpenAI + saisie manuelle). Conservés au plus en fallback/debug.

**OpenAI** ✅ : endpoint **Responses API** (`/v1/responses`), sortie **JSON structuré strict** + fallback `json_object`. Champs : `quartier_intro`, `transport_metro_texte`, `transport_bus_texte`, `transport_taxi_texte`. Le LLM peut **halluciner une ligne/station** → **saisie manuelle toujours possible** (invariant produit).

---

## 5. Invariants produit (à ne jamais casser)

1. **Données générales saisies une fois**, partagées Estimation/Mandat/Book (session).
2. **Tout champ enrichi reste modifiable** manuellement (l'auto ne verrouille jamais l'utilisateur).
3. **Bouton « Rafraîchir les calculs »** : recalcule les revenus **sans** relancer OpenAI/POI/images/géocodage.
4. **3 scénarios visibles dans l'UI** (pas seulement dans le PPTX).
5. **GenerationReport + validation de template** conservés (tokens restants, shapes/images manquants, mode strict).
6. **Templates = source de vérité visuelle** ; l'app ne reconstruit jamais le design.
7. **Règle devise** : si l'app injecte une valeur contenant « € », le template ne doit pas ajouter un « € » après le token (sinon `3 276 € €`).

---

## 6. Architecture cible (refonte)

- **Une seule couche de services** (fin de la double `app/services/` + `services/` à couplage bidirectionnel).
- **Une couche HTTP commune** (timeout + retry + backoff + UA) réutilisée par tous les appels JSON.
- **Remplacement de tokens robuste multi-runs** (PPTX & DOCX) : reconstruire le texte complet du paragraphe, remplacer, préserver préfixe/suffixe. C'est la cause du bug « texte après le token supprimé ».
- **OpenAI** : SDK officiel `openai` **ou** couche `requests` durcie (retry 429/5xx, modèle + `max_output_tokens` configurables).
- **UI** repensée pour l'autonomie : onglet **Clés API** couvrant **tous** les providers (saisie + test + statut + « où l'obtenir » + rerun auto), onboarding première utilisation, indicateur de disponibilité.
- **Streamlit Cloud-first** : pas de dépendance disque non persistant pour la logique ; `session_state` géré proprement (pattern *pending buffer* + `st.rerun()`).

---

## 7. Points ouverts métier

Voir `02-points-ouverts-client.md`. Les 3 bloquants de spec (non bloquants pour builder, mais à
confirmer avant recette finale) : **(1)** justification du 30,46 CD ; **(2)** relation taux/jours MD ;
**(3)** règle d'arrondi exacte des frais/scénarios. En attendant : on **reproduit les 2 jeux de
référence client** (qui font foi) et on documente l'hypothèse.
