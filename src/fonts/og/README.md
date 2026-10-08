# Polices embarquées — cartes OG

Deux fichiers Inter (régulier 400, gras 700) et un fichier Bebas Neue (400)
commités pour le rendu Satori des cartes Open Graph. Cf. ADR 0029.

Bebas Neue est la police des titres du site. Les cartes de partage
« Étiquette » (retenues après l'audit d'interface du 2026-10-07) la
reprennent pour le chiffre géant et le titre : sans elle, Satori retombait
sur Inter et la carte ne ressemblait plus au site. Sous-ensemble « latin » :
il couvre les accents, Œ/œ, le point médian et l'apostrophe typographique.

## Licence

**Inter** par Rasmus Andersson — SIL Open Font License 1.1.

Texte complet : https://github.com/rsms/inter/blob/master/LICENSE.txt

Cette licence permet :
- redistribution avec ou sans modification ;
- usage commercial ;
- embarquement dans des produits dérivés.

Sous condition de conserver la notice de copyright et la licence — ce
que fait ce README et le fichier `NOTICE` à la racine du repo.

**Bebas Neue** par Dharma Type — SIL Open Font License 1.1, texte complet
dans `LICENSE-bebas-neue` (copié du paquet `@fontsource/bebas-neue`).

## Mise à jour

Les fichiers `inter-latin-{400,700}-normal.woff` proviennent du package
`@fontsource/inter` (lui-même dérivé du repo Inter officiel). En cas de
mise à jour majeure, copier les nouveaux WOFF depuis
`node_modules/@fontsource/inter/files/` et committer. Même chose pour
`bebas-neue-latin-400-normal.woff`, depuis `@fontsource/bebas-neue`.
