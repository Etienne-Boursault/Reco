# ADR 0055 — Modèle canonique : l'œuvre, la citation, l'épisode

- **Statut** : Proposée (passe à « Acceptée » après le PoC sur la saison 6)
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : remplacera ADR 0005 (cohabitation) une fois acceptée ; ADR 0056
  (identifiants permanents) ; ADR 0061 (invariants) ;
  [`docs/v2/contrats-canoniques.md`](../v2/contrats-canoniques.md) ;
  [`DATA_SCHEMA.md`](../../DATA_SCHEMA.md)

## Contexte

Une citation existe aujourd'hui en deux copies : la reco (`recos/`), que lisent
les cartes des pages d'épisode, et la mention (`mentions/`), que lit la
chronologie des fiches. Chaque reco recopie aussi le titre, le créateur, les
types et les liens de son œuvre (`items/`). La relecture corrige la reco ; la
publication ne recopie vers la mention qu'à sa création ; la fiche, créée
depuis la reco, n'est plus mise à jour. Les copies divergent.

Mesuré au commit `7c2bf3f3` sur les 1 298 recos validées :

| Champ | Écarts entre la reco et sa mention ou son œuvre |
|---|---|
| `guestWork` | 197, tous « `true` sur la reco, absent sur la mention » |
| `creator` | 138 : 59 valeurs différentes, 69 seulement sur la reco, 10 seulement sur l'œuvre |
| `title` | 25, dont 22 par la casse seulement |
| `year` | 17, toujours présent d'un seul côté |
| `types` | 8 (l'œuvre cumule les types de ses citations) |
| `recommendedBy` | 2 |

975 recos validées n'ont aucun écart sur les neuf champs comparés. Les liens
n'existent que sur les recos : aucune œuvre n'a de champ `links`.

Sur les 59 créateurs contradictoires, la fiche affiche une plateforme ou
« Non précisé » (19 cas), une faute de transcription (10) ou un co-créateur de
moins (25). L'outil `tools/aligner_titres_item_reco.py` (19 août) propageait
déjà les corrections de la reco vers l'œuvre, pour la même raison : les recos
ont été relues une à une, pas les fiches.

La publication par révisions (ADR 0058) a besoin d'un modèle où chaque champ a
une seule valeur. Décision du 24/10 : « modèle canonique d'abord, SQLite
ensuite ».

## Décision

- **Trois entités.** L'**œuvre** porte ce qui la décrit : titre, créateur,
  types, année, alias, identifiants externes et **tous ses liens**. La
  **citation** (la mention) porte ce qui dépend de l'épisode : épisode,
  minutage, phrase citée, qui recommande, nature (`reco` ou `citation`),
  `guestWork`, statut, note. L'**épisode** reste inchangé.
- **Un seul propriétaire par champ.** La table complète est dans
  `docs/v2/contrats-canoniques.md` §2. La reco devient une **vue calculée**
  (œuvre + citation + épisode) : les pages reçoivent la même forme
  qu'aujourd'hui.
- **Aucun lien sur la citation** (décision du 24/10). Une version précise qui
  doit avoir son propre lien (un live, une édition) est une œuvre à part.
- **Valeurs.** Dans une révision, pas de `null` : un champ est présent ou
  absent. Un drapeau vaut `true` ou est absent. Une liste vide équivaut à son
  absence. Les énumérations sont explicites. Une chaîne vide est signalée,
  jamais effacée en silence.
- **Classes d'écart**, pour aligner les deux copies actuelles :
  - C1, la même chose écrite autrement (texte ou nombre, deux formes d'une même
    URL) : correction automatique, après une approbation unique de la liste des
    règles ;
  - C2, une seule copie porte la valeur : on la garde, par lot approuvé ; une
    valeur suspecte venue de la fiche (« TF1 », « Netflix », « Deezer »,
    « Dailyo ») est signalée, pas recopiée ;
  - C3, deux valeurs différentes : toujours décidé par l'éditeur, avec un défaut
    proposé : la reco pour le titre et le créateur, l'œuvre pour les types, la
    reco pour « recommandé par » (décision du 24/10) ;
  - C4, une citation rattachée à la mauvaise œuvre : relecture, fusion ou
    scission.
- **Décisions du 24/10 sur les données existantes.** Les 197 `guestWork` sont
  alignés en un lot (« la reco fait foi »). Deux écritures d'une même URL
  prennent une forme fixe par plateforme, selon une liste fermée de règles. Un
  conflit réel de liens n'a pas de défaut : toutes ses URL restent sur l'œuvre,
  signalées, jusqu'à la décision.
- **Requalifier une citation** (étoile, simple mention, statut) passe par une
  seule commande, `requalifierMention()`, qui écrit la mention puis la reco,
  sous le verrou du pipeline.
- **Écritures du corpus** : seulement par lots, chacun autorisé par l'éditeur,
  avec son fichier d'arbitrage et la liste des pages qui changent.

## Conséquences

- Positives : la carte et la fiche disent la même chose ; une correction se
  fait à un seul endroit ; la révision publiée est normalisée.
- Négatives : une transition où les recos JSON restent des miroirs, recalculés
  à chaque écriture, jusqu'à la migration de tous les écrivains ; huit lots à
  autoriser ; 93 contradictions à trancher au 24/10.
- Notes : le PoC sur la saison 6 vérifie neuf cas difficiles et la fidélité de
  l'aller-retour avant l'acceptation. Un cliquet refuse tout écart nouveau par
  rapport à une référence datée (ADR 0061). Les épisodes publics restent à
  confirmer par l'éditeur (DV-08).
