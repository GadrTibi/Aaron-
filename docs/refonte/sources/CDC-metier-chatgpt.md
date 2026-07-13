# Source — Document de transmission métier (ChatGPT), 2026-07-13

**Origine** : projet ChatGPT ayant servi au développement initial de MFY/Aaron.
**Avertissement PM (Gad)** : la discussion d'origine était très longue → **risque
d'hallucinations**. Ce document est une **source d'intention à trianguler**, PAS une
vérité. En cas de conflit, priment : **le code, les templates Office, les tests, et les
chiffres de référence client**.

## Statut de triangulation (2026-07-13)
Points **vérifiés concordants** avec le code/templates/tests (✅ fiables) :
- Coefficients scénarios CD 0,88/1,00/1,15 et MD 0,93/1,00/1,06 (code + tests).
- Rayon POI par défaut 300 m (`DEFAULT_RADIUS_M`).
- Frais de ménage supprimés partout (0 résidu code/config/templates).
- Commission MFY 15 %, base commission = brut − frais plateforme.
- CD basé sur 30,46 (constante `ESTIMATION_DAYS_PER_MONTH_CD`) + test de recette.
- Tokens des templates estimation/book : 100 % couverts par le code.
- OpenAI via Responses API + JSON structuré ; UA Nominatim présent.

Points **divergents / ouverts** (⚠️/❓, cf. `../02-points-ouverts-client.md`) :
- Arrondi MD : verbatim client 492 €/910 € vs `round()` = 491/909.
- Justification métier du 30,46 CD non fournie.
- Relation taux/jours MD à confirmer.

## Contenu intégral
Le document de transmission complet (8 sections : besoin métier, 3 livrables, règles de
calcul CD/MD, sources externes, décisions/arbitrages, ce qui n'est pas terminé, templates,
tests de recette) a été fourni par le PM et **intégré/triangulé dans
`../00-CDC-REFERENCE.md`**. Les jeux de référence CD et MD y sont repris comme tests de
recette permanents. Se référer au CDC de référence comme source de vérité travaillée.
