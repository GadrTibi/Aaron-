---
name: mfy-refonte-gate
description: MFY refonte (lots A/B/C) — faits durables/non-évidents à re-vérifier lors des prochains gates, pas à re-découvrir
metadata:
  type: project
---

# MFY refonte — mémoire de gate (branche refonte-propre vs main)

Faits **non-évidents** établis lors de l'audit adversarial du 2026-07-13. À re-vérifier
contre le code courant avant de s'appuyer dessus (peut avoir bougé).

## Chiffres MD 491 vs 492 (point ouvert P3) — math figée
- Verbatim client (CDC §3.2, marqué ✅) : MD frais plateforme **492 €** / frais généraux **910 €**.
- Code : `platform_fee = round(3276 × 0,15) = round(491,4) = 491` → frais **909 €**.
- **492 est INATTEIGNABLE** par toute règle d'arrondi propre qui reproduit AUSSI le jeu CD
  (CD `round(695,1)=695` exact ; `ceil` casserait CD en 696). Donc l'objectif CDC « une règle
  d'arrondi qui reproduit EXACTEMENT les 2 jeux » est mathématiquement impossible tel quel.
- **Why:** évite de re-chasser cet écart à chaque gate ou de le re-flag comme bug de calcul.
- **How to apply:** le vrai reste-à-faire = MFY confirme sa règle (ceil ? base non arrondie ?) OU
  la CDC §3.2 doit être dé-✅. Tant que non tranché, ne pas re-signaler comme régression neuve —
  c'est P3, connu. Le test `test_md_matches_client_numbers` assert 491/909 (le code, pas le verbatim).

## Token DOCX — motif `«\w+»` (lot C) : hole latent invariant 5
- `DOCX_TOKEN_PATTERN = «\w+»` pilote `_collect_leftovers` (docx_fill.py) → `add_missing_tokens(blocking=strict)`.
- Les 2 templates mandat (cd + md) ont **22 tokens réels, tous `\w+`** — aucun espace/tiret/apostrophe.
  Motif SÛR pour l'existant. Les 4 exclusions voulues = termes juridiques (« Mandant/Bien/Mandataire/
  Notice d'Information »).
- **Risque latent :** un token futur avec espace/tiret/apostrophe deviendrait invisible au garde-fou
  « document incomplet » → doc incomplet livré en silence. Motif code une FORME, pas l'INTENTION (anti-pattern règle 68 du 2026-07-09).
- **How to apply:** à chaque évolution des templates mandat, re-extraire les tokens (`«[^»]+»`) et
  vérifier que tout nouveau vrai token reste `\w+`, sinon le garde-fou le rate.

## Chaîne images supprimée (lot A) — sûre mais résidus orphelins
- `image_fetcher/image_search/image_cache/http_fetch` : **aucun import Python vivant** (vérifié). Pipeline
  images vivant = `services/wiki_images.py` (Wikimedia), pas la chaîne supprimée. Suppression sûre.
- Résidus orphelins laissés : `docs/PROJECT_MAP.json`, `docs/PROJECT_CONTEXT.md`, `docs/RISK_REGISTER.md` (R4),
  et surtout `app/services/provider_status.py` (vivant, affiché UI Clés API) qui offre encore
  **Unsplash/Pexels** (clés `UNSPLASH_ACCESS_KEY`/`PEXELS_API_KEY`) sans aucun consommateur. CDC §4 les
  liste aussi « (cascade) » → contredit le code.
- **How to apply:** si un nettoyage « images » repasse, ces orphelins sont le reste à traiter.

## Cache transport (lot A) — fix Windows OK, mais divergent
- `_safe_filename` (sub des chars illégaux `[<>:"/\\|?*]` → `_`) corrige l'OSError Windows ; round-trip OK
  (couvert implicitement par `test_transport_cache_hit`, clé à `:`). provider_order fixe = (gtfs,osm,google)
  → pas de collision réaliste.
- Divergent des caches frères `geocode_cache.py` / `cache_utils.py` qui **hachent la clé (sha1)** — approche
  plus robuste (collision/longueur/noms réservés). Nitpick de cohérence, pas un bug.
