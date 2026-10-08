# ADR 0051 — Conventions d'interface : appui, survol, cibles, couleur d'accent

- **Statut** : Acceptée
- **Date** : 2026-10-07
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0022 (a11y WCAG AA), rapport
  [`interface-rapport-2026-10-07`](../interface-rapport-2026-10-07.md)

## Contexte

Deux audits d'interface le même jour ont relevé des défauts qui tenaient
moins à une page qu'à l'absence de règle commune : aucun état `:active` dans
tout le site, des survols qui restaient collés au doigt, des cibles de 13 à
16 px, des grands chiffres tantôt jaunes tantôt blancs, des emojis de type à
côté d'icônes au trait, et un verbe (« Reco de », « Présentée par ») qui
contredisait parfois la section où il apparaît. Chaque nouvelle page les
aurait reproduits.

## Décision

**Toucher et survoler**

- Tout élément interactif répond à l'appui (`:active`, ~80 ms), avant le
  relâchement.
- Les survols qui soulèvent, bordent ou colorent sont réservés à
  `@media (hover: hover) and (pointer: fine)`. Le focus clavier n'en dépend
  pas.
- Pas de `transition: all` : on nomme les propriétés animées.

**Cibles**

- 44 px de zone sensible au minimum, obtenus par pseudo-élément ou par
  rembourrage compensé d'une marge négative, pour ne rien décaler.
- Les liens de retour (`a.back`, `.back > a`, `.retour > a`) passent
  au-dessus de ce qui les suit (`global.css`) : un grand titre qui déborde
  ne doit pas capter leurs clics.
- Sur téléphone, un élément trop dense pour 44 px (la frise d'une œuvre)
  cesse d'être une cible au doigt, à condition que les mêmes liens existent
  à la bonne taille juste à côté.

**Couleur d'accent**

- Les grands chiffres sont dans la couleur d'accent, partout.
- Les types s'illustrent par des icônes au trait dans la couleur d'accent
  (`src/utils/iconesTypes.ts`), jamais par des emojis.
- Une bordure d'accent signale le survol ; on ne s'en sert pas pour
  distinguer un contenu au repos (fond teinté à la place).

**Typographie**

- Interlettrage nul ou négatif aux grands corps, jamais positif ;
  milliers séparés par une espace insécable
  ordinaire (l'espace fine disparaît en Inter).

**Vocabulaire des mentions** (`src/utils/verbeMention.ts`)

- « Présentée par X » seulement si X est parmi les créateurs de l'œuvre ;
  sinon « Reco de X » (cartes) ou « Recommandée par X » (chronologie).
  `guestWork` signifie « œuvre de quelqu'un présent dans l'épisode », pas
  « œuvre de la personne qui en parle ».

## Conséquences

- Positives : une page nouvelle hérite des règles au lieu de les redécouvrir ;
  l'audit suivant peut les vérifier une à une.
- Négatives : le jaune perd une part de sa rareté ; l'éditeur l'a préféré à
  l'incohérence.
- Notes : Safari iOS n'applique `:active` qu'avec un écouteur `touchstart`
  (passif, dans `Layout`) ; le retirer désactive silencieusement l'appui sur
  iPhone.
