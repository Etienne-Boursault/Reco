# Polices embarquées — cartes OG

Deux fichiers Inter (régulier 400, gras 700) commit pour le rendu Satori
des cartes Open Graph. Cf. ADR 0029.

## Licence

**Inter** par Rasmus Andersson — SIL Open Font License 1.1.

Texte complet : https://github.com/rsms/inter/blob/master/LICENSE.txt

Cette licence permet :
- redistribution avec ou sans modification ;
- usage commercial ;
- embarquement dans des produits dérivés.

Sous condition de conserver la notice de copyright et la licence — ce
que fait ce README et le fichier `NOTICE` à la racine du repo.

## Mise à jour

Les fichiers `inter-latin-{400,700}-normal.woff` proviennent du package
`@fontsource/inter` (lui-même dérivé du repo Inter officiel). En cas de
mise à jour majeure, copier les nouveaux WOFF depuis
`node_modules/@fontsource/inter/files/` et committer.
