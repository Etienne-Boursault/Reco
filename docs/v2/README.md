# Reco V2 — publier sans rebuild

La V2 doit permettre de publier une correction sur le site sans PR, sans CI et
sans rebuild : venus construit une version signée du catalogue, l'éditeur
l'approuve, le site la sert. Avant cela, les données sont normalisées : chaque
champ n'a plus qu'un seul propriétaire.

Ce dossier rassemble ce qui est versionné de la conception :

| Fichier | Contenu |
|---|---|
| [`contrats-canoniques.md`](contrats-canoniques.md) | Spécification du modèle : propriété des champs, valeurs, classes d'écart, liens, ensembles publics, identité, requalification, fixtures et tests |
| [`decisions.json`](decisions.json) | Statut de chaque décision (`tranché`, `différé`, `bloquant`) et graphe des PR |
| ADR [0055](../adr/0055-modele-canonique.md), [0056](../adr/0056-identifiants-oeuvre-permanents.md), [0058](../adr/0058-publication-par-revisions.md), [0059](../adr/0059-approbation-publication.md), [0060](../adr/0060-autorite-editoriale-sauvegardes.md), [0061](../adr/0061-invariants-catalogue-public.md), [0062](../adr/0062-orientation-community-cloud.md) | Les décisions d'architecture, au statut « Proposée » |

Le numéro 0057 est réservé par un brouillon tenu hors du dépôt.

## Avant de commencer une PR

```bash
node scripts/verifier-prerequis.mjs PR-03            # 0 : prérequis remplis ; 1 : décision bloquante
node scripts/verifier-prerequis.mjs PR-03 --sortie   # avant la fusion
```

Une décision `bloquant` bloque sa première PR et toutes celles qui en
dépendent. Le script ne sait pas quelles PR sont fusionnées : le graphe ci-dessous
le dit.

## Règles communes

- Une PR fusionnée qui touche `tools/` ou `deploy/venus/` est active sur venus
  au passage suivant de `tick.sh`, dans les 10 minutes : une fusion est un
  déploiement. Tout comportement nouveau qui **écrit des données** arrive
  derrière une variable du `.env` de venus, désactivée par défaut, que
  l'éditeur active.
- Toute écriture du corpus demande une autorisation explicite de l'éditeur,
  lot par lot, avec la liste des pages qui changent.
- Une valeur citée dans une PR est mesurée par la PR, ou marquée « non
  mesurée ».

## Décisions prises le 24 octobre 2026

| Décision | Choix |
|---|---|
| Orientation | Community + Cloud ; spécification du Cloud non arbitrée (ADR 0062) |
| Ordre | Modèle canonique d'abord, SQLite ensuite |
| Sauvegarde | Hors site depuis venus, chaque nuit ; perte de 24 h au plus acceptée (ADR 0060) |
| Essai | PoC sur la saison 6 et ses 17 mentions de fermeture, avant d'aligner le corpus |
| Phase 0 | Feu vert pour PR-00, PR-01, PR-02 et le PoC |
| DV-09 | Un titre de fiche fusionnée cité de nouveau est rattaché à la fiche gardée, annoncé et refusable ; le registre des ids est dérivé de l'historique Git, ni versionné ni déployé (ADR 0056) |
| DV-03 | En cas de contradiction, défaut proposé : la reco pour `title` et `creator`, l'œuvre pour `types` (ADR 0055) |
| DV-04 | Les 197 `guestWork` divergents : un lot, « la reco fait foi » |
| DV-02 | Deux écritures d'une même URL : une forme fixe par plateforme |
| DV-01 | Conflit de liens : gel ; **aucun lien sur la citation**, les liens appartiennent à l'œuvre |

Les décisions encore ouvertes, avec la PR qu'elles bloquent, sont dans
`decisions.json`.

## Plan des PR

**Phase 0, prêtes à démarrer** : aucune n'écrit le corpus ni ne change le rendu.

| PR | Objet |
|---|---|
| PR-00 | Ces documents, `decisions.json` et `scripts/verifier-prerequis.mjs` |
| PR-01 | Invariants et comptes du corpus, avec une référence datée des écarts (ADR 0061) |
| PR-02 | Port `CatalogReader` : une seule porte d'entrée pour lire les données ; `dist/` identique |
| PoC-S6 | Essai du modèle sur la saison 6 et neuf fixtures, sur une branche jamais fusionnée |

**Identité et modèle**

| PR | Objet | Après |
|---|---|---|
| PR-ID | Registre des identifiants (ADR 0056) | PR-01 |
| PR-01b | Fusion sûre : citations repointées avant la suppression, écritures atomiques | PR-01, PR-ID |
| PR-MC | Modèle et vue reco, en code seulement | PoC concluant, PR-02 |
| PR-MC-sync | `requalifierMention()`, seul chemin pour requalifier une citation | PR-MC, PR-ID |
| PR-MC-donnees | Alignement du corpus en huit lots autorisés un à un | PR-MC-sync, PR-ID |
| PR-MC-outils-2 et 3 | La relecture et `chercher-liens` écrivent chez le propriétaire, puis les autres outils | PR-MC-donnees |

**Publication par révisions** (ADR 0058, 0059, 0060)

| PR | Objet | Après |
|---|---|---|
| PR-SONDE | Sonde inerte chez l'hébergeur, pour mesurer ce que le protocole suppose | PR-00, autorisation |
| PR-03 | Constructeur de révisions, déterministe | PR-MC, DV-08 |
| PR-04 | Magasin de révisions et lecteur, un instantané par requête | PR-02, PR-03 |
| PR-05 | Routes rendues à la demande, parité avec le statique sur toutes les routes | PR-04, PR-MC-donnees |
| PR-06 | Ressources dérivées versionnées (recherche, cartes), ETag | PR-05 |
| PR-07 | Ingestion, activation concurrente sûre, restauration | PR-04, PR-SONDE |
| PR-07b | Écran « Publier » et registre d'approbation | PR-07 |
| PR-10 | Ressources (vignettes) transférées avec la révision | PR-07 |
| PR-CUT | venus seul écrivain, instantané de sauvegarde, restauration exercée | PR-07b, PR-10, PR-MC-outils-2 |
| PR-08 | Bascule : phase 8a, puis 8b | PR-06, PR-CUT, liste de contrôle verte |

**Après la bascule** : export statique depuis une révision (PR-11) ; image
Community avec sauvegarde et restauration (PR-12) ; SQLite en lecture fantôme
(PR-13), puis comme écrivain, ce qui met fin aux miroirs (PR-14) ;
autorisations par canal de diffusion (PR-15) ; temps déclaré et estimation
(PR-16).
