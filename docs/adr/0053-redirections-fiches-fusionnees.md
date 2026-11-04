# ADR 0053 — Redirections permanentes des fiches d'œuvre fusionnées

- **Statut** : Acceptée
- **Date** : 2026-10-21
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0032 (page œuvre canonique), PR #118

## Contexte

Fusionner deux fiches d'œuvre en double (même film sous deux titres, même
artiste sous deux graphies) supprime la fiche perdante. Son adresse
`/<source>/oeuvre/<id>`, déjà indexée par les moteurs et parfois partagée,
répondait alors 404. L'audit du 2026-10-20 a demandé neuf fusions de plus, et
264 fusions passées avaient déjà laissé autant d'adresses mortes.

## Décision

- Les outils de fusion (`fusionner_doublons_cures.py`,
  `fusion_items_doublons.fusionner`) notent chaque ancienne adresse dans
  `src/content/redirections-oeuvres.json` **avant** de supprimer la fiche, via
  `tools/redirections_oeuvres.py`. Une chaîne A → B → C est raccourcie en
  A → C.
- `src/server/redirections.mjs` répond à ces adresses par un **301** vers la
  fiche survivante, avant tout autre traitement. Une table absente ou
  illisible donne une table vide : elle coûte des 404, jamais le site.

## Conséquences

- Positives : les moteurs transfèrent la page ; un lien partagé mène toujours
  à l'œuvre. 274 entrées à la mise en service.
- Négatives : la redirection ne vit que dans `server.mjs`. Un déploiement
  purement statique (sans serveur Node) n'en profite pas.
- Notes : neuf cibles de la table n'ont pas de page (œuvre sans mention
  validée) et mènent à une 404 — à revoir si elles reçoivent du trafic.
