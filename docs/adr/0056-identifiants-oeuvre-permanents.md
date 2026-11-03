# ADR 0056 — Identifiants d'œuvre permanents

- **Statut** : Acceptée (2026-11-01), à la validation de la documentation ; acceptée sur le principe le 2026-10-25
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : amende ADR 0003 (identité typée) et ADR 0053 (redirections des fiches fusionnées) ; ADR 0055 (modèle canonique) ; ADR 0060 (autorité éditoriale)

## Contexte

L'identifiant d'une fiche figure dans son adresse (`/<source>/oeuvre/<id>`). `generate_item_id` le calcule à partir du titre et du créateur. Le rapprochement de `publier_episode` ne connaît que les fiches vivantes, sans leurs alias ni leurs anciens titres.

Mesuré au commit `7c2bf3f3` :
- 277 identifiants ont été retirés dans l'historique Git ;
- pour 235 d'entre eux, la chaîne redonnerait **le même identifiant** à une nouvelle œuvre de même titre et créateur ;
- 233 de ceux-là sont la source d'une redirection 301. La nouvelle fiche existerait, mais son adresse renverrait ailleurs, et la citation n'apparaîtrait sur aucune fiche visible ;
- une redirection part aussi d'une fiche vivante.

## Décision

- **Un identifiant n'est jamais redonné.** Un registre connaît tous les identifiants émis, leur état (vivant, fusionné, supprimé) et toutes les clés qu'ils ont portées : titre et créateur actuels, anciens titres, alias.
- **Le registre n'est ni versionné ni déployé.**
  - Tant que le corpus vit dans Git, il est **calculé à partir de l'historique Git** à chaque émission : 1,1 s pour 564 commits, mesuré sur un portable. Le module refuse de tourner sur un clone superficiel.
  - Quand venus devient le seul écrivain des données, hors de Git (ADR 0060), le registre est écrit une fois dans ses données, puis vérifié. Cela se fait avant que le dépôt de code ne reparte d'un historique neuf.
  - Le site n'en a jamais besoin : il ne lit que les redirections.
- **Rattachement d'un nouveau candidat**, avant toute émission :
  - clé d'une fiche vivante, avec un type commun : rattachement ;
  - clé d'une fiche **fusionnée** : rattachement automatique à la fiche gardée. Il est annoncé à l'éditeur en fin d'épisode et à la relecture, où l'éditeur peut le refuser ;
  - clé d'une fiche supprimée sans fusion : identifiant neuf, signalé ;
  - clé qui désigne plusieurs fiches vivantes : signalée, jamais tranchée par l'ordre des identifiants.
- **Cycle de vie** :
  - corriger un titre ne change pas l'identifiant, et l'ancienne clé reste ;
  - une fusion passe la fiche perdante à « fusionnée », avec sa cible, après avoir repointé ses citations ;
  - une scission qui sépare l'ancienne fiche réactive son identifiant et retire la redirection ;
  - une suppression sans fusion répond 404.
- **Les redirections** sont déduites du registre, et elles font partie de chaque publication : une fusion prend effet avec la publication qui la porte.
- **Un seul module** émet, rattache, fusionne, scinde et supprime. Un test interdit tout appel à `generate_item_id` et toute suppression de fiche en dehors de lui. La migration qui réécrit les œuvres depuis les recos refuse de tourner dès que le registre est actif.

## Conséquences

- **Positives** : plus aucune page masquée par une redirection ; les fusions déjà décidées sont respectées ; les adresses partagées restent stables.
- **Négatives** : une vraie œuvre homonyme d'une fiche fusionnée serait rattachée à tort, mais sous les yeux de l'éditeur, qui peut refuser. Le calcul exige un clone complet.
- **Notes** : livré derrière une variable de l'atelier, désactivée par défaut. La durée du calcul sur venus reste à mesurer.
