# Points ouverts à confirmer avec le client MFY

> Ces points **ne bloquent pas** la refonte : en attendant, on **reproduit les jeux de
> référence client** (qui font foi) et on documente l'hypothèse retenue. Ils doivent être
> **confirmés avant la recette finale** (mise en production réelle chez MFY).

| # | Question | Hypothèse retenue en attendant | Impact si faux |
|---|---|---|---|
| **P1** | **Base de jours CD** : pourquoi **30,46** j/mois et non 30 ? Est-ce la vraie règle métier ou une calibration sur un screenshot ? | On garde **30,46** (reproduit le jeu de référence 4 634 €). Jours *affichés* = `floor(occ×30)`. | Tous les revenus CD décalés ; incohérence calcul (30,46) vs affichage (30) visible par un propriétaire attentif. |
| **P2** | **Relation taux/jours en MD** : le taux (83 %) est **affiché** mais ne multiplie pas le revenu (piloté par les jours). Confirmé ? Que faire si l'utilisateur saisit taux et jours incohérents (ex. 50 % + 26 j) ? | Jours pilotent le revenu ; taux purement affiché. Pas de garde-fou de cohérence. | Revenu MD faux si le client attendait taux×jours ; ou affichage incohérent. |
| **P3** | **Règle d'arrondi exacte** des frais/scénarios. Le verbatim MD donne plateforme **492 €** / frais **910 €**, alors que `round(491,4)=491`. Arrondi au supérieur ? demi-entier ? | On choisira la règle qui **reproduit exactement les 2 jeux de référence** (Lot B) et on la documente. | Écarts de 1–2 € sur les documents ; perte de confiance client sur les chiffres. |
| **P4** | **Book** : specs de contenu réelles (parcours d'accès type, sections obligatoires, format PDF attendu) ? | On finalise au niveau atteignable avec l'existant + tokens connus. | Book livré incomplet / non conforme aux attentes. |
| **P5** | **Confidentialité** : l'adresse du bien est transmise à des services externes (Google, OpenAI…). MFY doit-il en informer / a-t-il des contraintes RGPD ? | À documenter, pas de blocage technique. | Enjeu conformité si données propriétaires sensibles. |

**Note** : le client final « métier » est **MFY**, pas le PM. Ces questions relèvent de MFY.
Le PM (Gad) porte le build/scope ; les réponses P1–P5 viennent de MFY.
