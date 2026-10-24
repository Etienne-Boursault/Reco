# ADR 0056 — Identifiants d'œuvre permanents

- **Statut** : Proposée
- **Date** : 2026-10-25
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0053 (redirections des fiches fusionnées) ; ADR 0003 (identité
  typée, différée) ; ADR 0055 (modèle canonique) ;
  [`docs/v2/contrats-canoniques.md`](../v2/contrats-canoniques.md) §6

## Contexte

L'identifiant d'une fiche figure dans son adresse (`/<source>/oeuvre/<id>`).
`generate_item_id` le calcule à partir du titre et du créateur, et le
rapprochement de `publier_episode` ne connaît que les fiches vivantes, sans
leurs alias ni leurs anciens titres.

Mesuré au commit `7c2bf3f3` : 277 identifiants ont été retirés dans
l'historique Git. Pour 235 d'entre eux, la chaîne redonnerait **le même
identifiant** à une nouvelle œuvre de même titre et créateur. 233 de ceux-là
sont la source d'une redirection 301 : la nouvelle fiche existerait, mais son
adresse renverrait ailleurs, et la citation n'apparaîtrait sur aucune fiche
visible. Une redirection part aussi d'une fiche vivante (`8b112235`).

## Décision

- **Un identifiant n'est jamais redonné.** Un registre connaît tous les
  identifiants émis, leur état (vivant, fusionné, supprimé) et toutes les clés
  qu'ils ont portées : titre et créateur actuels, anciens titres, alias.
- **Le registre n'est ni versionné ni déployé** (décision du 24/10). Tant que le
  corpus vit dans Git, il est **dérivé de l'historique Git** à chaque émission :
  1,1 s pour 564 commits, mesuré sur un portable. Un cache non suivi peut le
  garder entre deux passages. Quand venus deviendra le seul écrivain du corpus,
  hors de Git (ADR 0060), le registre sera stocké avec ses données éditoriales.
  Le site n'en a jamais besoin : il ne lit que les redirections.
- **Rattachement d'un nouveau candidat**, avant toute émission :
  - clé égale à celle d'une fiche vivante, avec un type commun : rattachement
    (règle actuelle) ;
  - clé égale à celle d'une fiche **fusionnée** : rattachement automatique à la
    fiche gardée, annoncé dans le message Matrix de fin d'épisode et à la
    relecture, où l'éditeur peut le refuser (décision du 24/10) ;
  - clé égale à celle d'une fiche supprimée sans fusion : identifiant neuf,
    signalé ;
  - clé qui désigne plusieurs fiches vivantes : signalée, jamais tranchée par
    l'ordre des identifiants.
- **Cycle de vie.** Corriger un titre ne change pas l'identifiant ; l'ancienne
  clé reste. Une fusion passe la fiche perdante à « fusionnée », avec sa cible,
  après avoir repointé ses citations. Une scission qui sépare l'ancienne fiche
  réactive son identifiant et retire la redirection. Une suppression sans
  fusion répond 404, comme aujourd'hui.
- **Un seul module** (`tools/domain/registre_oeuvres.py`) émet, rattache,
  fusionne, scinde et supprime. Un test statique interdit tout appel à
  `generate_item_id` et toute suppression de fiche hors de lui.
  `migrate_reco_to_item_mention.py --apply` refuse de tourner dès que le
  registre est actif.

## Conséquences

- Positives : plus aucune page masquée par une redirection ; les fusions déjà
  décidées sont respectées ; les adresses partagées restent stables.
- Négatives : une vraie œuvre homonyme d'une fiche fusionnée serait rattachée à
  tort, mais sous les yeux de l'éditeur, et refusable. La dérivation exige un
  clone complet : le module refuse de tourner sur un clone superficiel.
- Notes : livré derrière la variable `RECO_REGISTRE_IDS`, désactivée par défaut
  (PR-ID). La durée de la dérivation sur venus reste à mesurer.
