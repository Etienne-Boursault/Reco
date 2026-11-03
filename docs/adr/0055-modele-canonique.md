# ADR 0055 — Modèle canonique : l'œuvre, la citation, l'épisode

- **Statut** : Acceptée sur le principe (2026-10-25) ; documentation validée le 2026-11-01 ; devient « Acceptée » après la reprise du cas F4 de l'essai
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : remplace ADR 0005 (cohabitation) ; ADR 0056 (identifiants permanents) ; ADR 0058 (publication) ; ADR 0061 (invariants) ; [`DATA_SCHEMA.md`](../../DATA_SCHEMA.md)

## Contexte

Une citation existe aujourd'hui en deux copies :
- la reco (`recos/`), que lisent les cartes des pages d'épisode ;
- la mention (`mentions/`), que lit la chronologie des fiches.

Chaque reco recopie aussi le titre, le créateur, les types et les liens de son œuvre (`items/`). La relecture corrige la reco ; la publication ne recopie vers la mention qu'à sa création ; la fiche, créée depuis la reco, n'est plus mise à jour. Les copies divergent.

Mesuré au commit `7c2bf3f3` sur les 1 298 recos validées :

| Champ | Écarts entre la reco et sa mention ou son œuvre |
|---|---|
| `guestWork` | 197, tous « vrai sur la reco, absent sur la mention » |
| `creator` | 138 : 59 valeurs différentes, 69 seulement sur la reco, 10 seulement sur l'œuvre |
| `title` | 25, dont 22 par la casse seulement |
| `year` | 17, toujours présent d'un seul côté |
| `types` | 8 |
| `recommendedBy` | 2 |

Les liens n'existent que sur les recos : aucune œuvre n'a de champ `links`. Sur les 4 610 liens des cartes, il y a 847 libellés différents pour 395 sites.

## Décision

- **Trois entités.**
  - L'**œuvre** porte ce qui la décrit : titre, créateur, types, année, alias, identifiants externes et **tous ses liens**.
  - La **citation** porte ce qui dépend de l'épisode : épisode, minutage, phrase citée, qui recommande, nature (`reco` ou `citation`), l'étoile « leur œuvre », statut, note.
  - L'**épisode** ne change pas.
- **Un seul propriétaire par champ.** La reco devient une **vue calculée** : œuvre, citation et épisode. Les pages reçoivent la même forme qu'aujourd'hui.
- **Aucun lien sur la citation.** Une version précise qui doit avoir son propre lien, comme un live ou une édition, est une œuvre à part.
- **Règles des liens :**
  - deux liens directs vers la même plateforme restent tous les deux ;
  - un lien de recherche est retiré s'il existe un lien direct vers la même plateforme ;
  - la carte montre le premier lien de chaque plateforme, la fiche les montre tous ;
  - aucune adresse n'est choisie en silence : deux adresses contradictoires restent toutes deux sur la fiche, signalées ;
  - une forme fixe d'adresse par plateforme, appliquée partout, selon une liste fermée de règles d'équivalence. Chaque adresse réécrite est vérifiée dans un vrai navigateur ;
  - les libellés suivent une seule règle d'écriture, « Plateforme » ou « Plateforme — précision », dont la liste est validée par l'éditeur ;
  - les listes « où regarder » jamais affichées sont vérifiées une à une avant toute publication. Un lien de recherche y est remplacé par le lien direct, ou supprimé. Les liens qu'on ne peut pas vérifier restent de côté, non publiés ;
  - chaque lien garde la date et l'état de sa dernière vérification, dans les données de l'atelier ; une veille régulière vérifie qu'il répond et qu'il mène à la bonne œuvre.
- **Graphie des titres** : chaque titre suit sa source de référence (Wikipédia en français quand l'œuvre y figure, sinon l'éditeur ou la plateforme). Une marque stylisée est soumise à l'éditeur.
- **Valeurs** : dans les données publiques, pas de `null`. Un champ est présent ou absent ; un drapeau vaut vrai ou est absent ; une liste vide équivaut à son absence ; les énumérations sont écrites ; une chaîne vide est signalée, jamais effacée en silence.
- **Classes d'écart**, pour aligner les copies actuelles :
  - **C1** : la même chose écrite autrement ; correction automatique, après une approbation unique de la liste des règles ;
  - **C2** : une seule copie porte la valeur ; on la garde, par lot approuvé. Une valeur suspecte venue de la fiche (une plateforme à la place d'un créateur) est signalée, pas recopiée ;
  - **C3** : deux valeurs différentes ; toujours décidé par l'éditeur. Le défaut proposé est la carte pour le titre et le créateur ; les types sont l'union de ceux de l'œuvre et de ses cartes ;
  - **C4** : une citation rattachée à la mauvaise œuvre ; relecture, fusion ou scission.
- **Les 197 étoiles « leur œuvre »** sont alignées en un lot : « la reco fait foi ».
- **Épisodes publics** : déjà en ligne, ou relus et finalisés. Un épisode n'est retiré que par une commande explicite, et ce retrait l'emporte sur tout autre état, jusqu'à une commande explicite qui le rétablit.
- **Requalifier une citation** (étoile, simple mention, statut) passe par une seule commande. Elle écrit la mention, puis la reco, sous le verrou de la chaîne.
- **Écritures du corpus** : seulement par lots, chacun autorisé par l'éditeur, avec ses décisions et la liste des pages qui changent.
- **Ce qui est publié** : une liste fermée, les seuls champs que les pages affichent.

## Conséquences

- **Positives** : la carte et la fiche disent la même chose ; une correction se fait à un seul endroit ; les données publiées sont normalisées ; plusieurs liens par plateforme deviennent possibles, et vérifiables.
- **Négatives** :
  - une transition pendant laquelle les recos JSON restent des miroirs, recalculés à chaque écriture, jusqu'à la migration de tous les écrivains ;
  - huit lots à autoriser, dont l'un demande une soixantaine de décisions ;
  - une carte peut changer de lien sans décision quand l'œuvre a deux liens vers la même plateforme : ce prix est accepté.
- **Notes** :
  - l'essai sur la saison 6 a passé 7 critères sur 8 ; le huitième (une carte ne garde qu'un lien par libellé) est rejoué avec la règle « premier lien de chaque plateforme » ;
  - un cliquet refuse tout écart nouveau par rapport à une référence datée (ADR 0061) ;
  - les personnes (invités, créateurs) restent des chaînes de caractères : aucune page n'a besoin d'une entité « personne » aujourd'hui.
