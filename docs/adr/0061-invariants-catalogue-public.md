# ADR 0061 — Invariants du catalogue public

- **Statut** : Acceptée (2026-11-01), à la validation de la documentation ; acceptée sur le principe le 2026-10-25
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : complète ADR 0012 (linter du dataset) ; ADR 0055 (modèle canonique) ; ADR 0056 (identifiants)

## Contexte

Rien ne vérifie automatiquement que le corpus est cohérent : doublons d'identifiant, citations orphelines, écarts entre la reco et sa citation ou son œuvre. Les mesures du 24/10 ont dû passer par des scripts ponctuels. Au commit `7c2bf3f3`, le corpus est sain sur ces points : 0 doublon, 0 erreur de lecture, et 8 mentions écartées sans reco.

## Décision

- **Une seule implémentation**, en TypeScript, utilisée par la CI, par le constructeur des publications et par le contrôle des sauvegardes.
- **Comptes par collection** : fichiers, identifiants distincts, doublons (listés, jamais écrasés), erreurs de lecture (code de sortie non nul), orphelins, écarts de statut entre reco et mention.
- **Règles bloquantes** : une redirection qui part d'une fiche vivante ayant une page ; un `recommendedBy` sur une œuvre ; un brouillon public ; un épisode retiré mais public ; un identifiant hors de son format fermé (ADR 0058) ; dans une liste de liens d'une œuvre, deux liens de même clé, ou des rangs qui ne se suivent pas ; un nom de vignette qui désigne deux fichiers.
- **Avertissements** : une redirection qui part d'une fiche vivante sans page ; une cible de redirection sans page (9 au 24/10).
- **Écarts par classe** (ADR 0055), comparés à une référence datée (`tests/fixtures/corpus/divergences-connues.json`), avec un cliquet dans les deux sens : un écart nouveau échoue, et un écart disparu doit être retiré de la référence.
- **Mise en service** : le travail de CI est d'abord non bloquant, puis bloquant après une semaine sans alerte.

## Conséquences

- **Positives** : une dérive du corpus se voit dans la PR qui l'introduit.
- **Négatives** : la référence datée doit être relue quand le corpus change.
- **Notes** : une règle bloquante rouge sur le vrai corpus se liste ; elle ne se corrige pas dans la PR des invariants.
