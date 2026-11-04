# ADR 0050 — Une carte de partage par œuvre, et un cache qui survit aux builds

- **Statut** : Acceptée
- **Date** : 2026-10-07
- **Décideurs** : équipe Reco
- **Liens** : ADR 0021 (SEO / OG / sitemap), rapport
  [`interface-rapport-2026-10-07`](../interface-rapport-2026-10-07.md) §3

## Contexte

Les cartes de partage (Open Graph) sont rendues au build par Satori puis
resvg. Seuls l'accueil et la source en avaient une ; une œuvre ou un épisode
partagés montraient la carte générique ou la vignette YouTube, qui ne dit
rien des recommandations.

La direction « Étiquette » (un panneau d'accent, un chiffre géant) a été
retenue pour l'accueil, les galeries, les épisodes et les œuvres. Les œuvres
n'en recevaient qu'à partir de deux mentions, pour limiter le coût au build.
L'éditeur a levé ce seuil : « avoir un build long n'est pas un souci ».

Deux constats en mesurant ce coût :

1. Le cache des cartes vivait dans `dist/.cache/og`. `astro build` vide
   `dist/` au début de chaque build : le cache n'avait jamais servi d'un
   build à l'autre (vérifié avec un fichier témoin).
2. Sa clé portait sur les données de la carte (titre, chiffres). Tant que le
   cache disparaissait, c'était sans conséquence ; persistant, il aurait
   resservi les anciennes images après une retouche du gabarit, sans que
   rien ne le signale.

## Décision

- Toute fiche d'œuvre a sa carte dès sa première mention
  (`MENTIONS_MIN_CARTE_OEUVRE = 1`, `src/lib/og/cartes.ts`).
- Le cache vit à la racine du dépôt, `.cache/og` (ignoré par git). Le
  déploiement (`git fetch && git reset --hard && npm run build`) ne touche
  pas aux fichiers ignorés : le cache survit d'un déploiement à l'autre.
- La clé est l'empreinte SHA-256 de l'**arbre** produit par le gabarit
  (styles et textes compris), des options de rendu et de l'empreinte des
  polices (`src/lib/og/renderer.ts`). Toute modification visible change la
  clé ; une carte inchangée est relue telle quelle.
- Le cache reste best-effort : une erreur d'écriture n'échoue jamais un build.

## Conséquences

- Positives : 1 073 cartes d'œuvre (1 202 PNG, 53 Mo). Build à froid 299 s,
  build suivant 21 s — plus rapide qu'avant les cartes (51 s), le cache
  évitant aussi l'accueil et les galeries.
- Négatives : le premier build chez l'hébergeur dure ~5 min. Le cache ne se
  purge pas : les images d'un gabarit abandonné restent sur disque
  (`rm -rf .cache/og` remet à zéro, au prix d'un build à froid).
- Notes : un `git clean -fdx` dans la procédure de déploiement effacerait le
  cache sans rien casser, mais chaque build redeviendrait un build à froid.
