# ADR 0004 — `SourceRef` sealed-class par média — DIFFÉRÉ

- Statut : Différée (revisite quand un 2e média est ajouté)
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Critique archi #9 : `SourceRef` est conçue pour un podcast (`source_id`,
`episode_guid`, `timestamp`, `transcript_source`). Si on ajoute un
support YouTube standalone, livre, blog, etc., les champs deviennent
nullables et la sémantique se dilue.

Refactor envisagé : hiérarchie sealed (`PodcastSourceRef`, `YouTubeSourceRef`,
`BookSourceRef`, …) avec un type discriminant.

## Décision

**Différer**. Aujourd'hui : 1 seul média (podcast), 12 mois de tests
production. Le coût refactor + complexité polymorphique n'est pas justifié.

## Conséquences

- `SourceRef` reste mono-podcast pour Phase 1.
- Trigger de revisite : à l'introduction d'un 2e média (YouTube
  standalone ou autre).
- Si revisite : créer ADR 0004-bis avec décision finale.
