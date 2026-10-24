# ADR 0062 — Orientation Community + Cloud

- **Statut** : Proposée (orientation décidée le 2026-10-24 ; spécification non
  arbitrée)
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : [`vision-2026.md`](../vision-2026.md), décision 4 ;
  [`roadmap-2026.md`](../roadmap-2026.md) ; ADR 0039 (licence MIT) ; ADR 0045
  (registre des sites)

## Contexte

La vision fixait trois décisions structurelles, sans trancher la forme
durable du projet au-delà du kit open-source. La revue d'architecture de la V2
devait savoir si une offre hébergée était envisagée, pour ne rien bâtir qui
l'empêche.

## Décision

- L'orientation **Community + Cloud** est décidée : le kit open-source pour les
  podcasts qui l'installent eux-mêmes, et une offre hébergée à venir.
- **Rien n'est arbitré** sur la spécification du Cloud, le multi-tenant ni le
  financement. Une instance isolée par client est une hypothèse, pas une
  décision.
- **Aucune fondation de la V2 ne dépend du Cloud.** Le registre des sites (ADR
  0045) reste en v1, sans champ nouveau.

## Conséquences

- Positives : la direction est écrite ; les choix de la V2 ne la ferment pas.
- Négatives : aucune.
- Notes : les refus de `roadmap-2026.md` (comptes utilisateurs, multi-rôles)
  restent valables tant que la spécification du Cloud n'est pas arbitrée.
