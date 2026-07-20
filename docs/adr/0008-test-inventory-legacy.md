# ADR 0008 — Test d'inventaire figé des imports legacy `Reco` / `Episode` / `RecoRepository`

Date : 2026-06-10
Statut : Acceptée

## Contexte

Suite à l'introduction de la couche `Item` / `Mention` (ADR 0001–0004) et de
la migration en deux phases (ADR 0007), les anciennes entités du domaine
(`Reco`, `Episode`, `RecoRepository`, `EpisodeRepository`, `TranscriptStore`)
restent **vivantes** dans `tools/domain/_legacy.py` le temps que les outils
historiques (rendu Astro, review_server, pipeline d'extraction) migrent.

L'ADR 0005 autorise explicitement cette cohabitation, mais sans garde-fou
**aucune nouvelle code path n'empêche les développeurs d'élargir la surface
legacy** par mégarde — chaque nouvelle dépendance complique d'autant la
suppression future.

## Décision

Ajouter un test d'inventaire **figé** qui :

1. scanne `tools/` à la recherche d'imports legacy (`from domain import Reco`,
   `Episode`, `RecoRepository`, etc.) ;
2. compare le set des fichiers détectés à une liste `FROZEN_USAGES`
   maintenue manuellement, datée du jour ;
3. échoue si un **nouveau** fichier apparaît dans la liste — forçant le
   contributeur à justifier l'ajout et à mettre à jour la frontière legacy
   explicitement (avec validation review).

## Conséquences

### Positives
- Visibilité directe de la dette legacy en CI (fail-fast).
- Réduction monotone garantie : retirer un fichier de `FROZEN_USAGES` exige
  juste de le supprimer du dict — pas de risque de réintroduction silencieuse.
- Coût quasi nul (un scan de fichiers, pas d'AST parsing).

### Négatives
- Faux positifs possibles si un commentaire mentionne le mot `Reco` :
  on filtre via `^from domain import ...` ou `from domain._legacy`.
- Maintenance manuelle de la liste — acceptée en pratique car le ratio
  modification de cette liste/an reste très bas.

### Neutres
- Pas de génération automatique : le contributeur DOIT lire l'erreur pour
  comprendre l'intention.

## Frontière legacy (à date)

Cf. `tests/test_legacy_imports_inventory.py::FROZEN_USAGES`.
