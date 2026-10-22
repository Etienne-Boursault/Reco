# ADR 0052 — Données des visiteurs : durées appliquées, aucun tiers à l'affichage

- **Statut** : Acceptée
- **Date** : 2026-10-22
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : ADR 0034 (signalements), ADR 0040 (manifeste), ADR 0046 (clics
  sortants), PR #119, #121, #122, #123, #125

## Contexte

`/mentions-legales` était demandée par les visiteurs et répondait 404. En
l'écrivant, trois écarts sont apparus entre ce que le site promet et ce qu'il
fait :

1. **Rien n'était jamais effacé.** Visites, clics et signalements (nom et
   e-mail facultatifs compris) s'accumulaient sans limite dans `tools/output/`
   sur le serveur de production.
2. **Le catalogue chargeait ses vignettes chez YouTube et Acast.** Chaque
   visiteur envoyait son adresse IP à Google sans avoir cliqué, alors que le
   manifeste annonce « aucun tracker tiers ».
3. **Le tableau d'audience comptait des robots comme des personnes.** Les
   préchargements au survol passaient pour des pages vues, et la moitié des
   requêtes venaient de scripts déguisés en navigateurs, sans
   `Accept-Language`.

Une page de mentions qui annonce une durée sans purge, ou l'absence de tiers
avec des images Google, serait mensongère.

## Décision

- **Les durées sont appliquées par le serveur lui-même.**
  `src/server/retention.mjs`, lancé par `server.mjs` au démarrage puis chaque
  jour, supprime les fichiers quotidiens de visites et de clics de plus de
  **13 mois** (durée de référence de la CNIL pour la mesure d'audience) et
  efface le nom et l'e-mail des signalements de plus de **12 mois** — le
  signalement reste, il retrace une correction. La page lit ses durées dans ce
  module : elles ne peuvent pas diverger.
- **Afficher une page ne contacte aucun autre service.** Les vignettes sont
  téléchargées une fois dans `public/vignettes/` (`tools/vignettes_episodes.py`)
  et servies par le site ; `src/utils/vignettes.ts` calcule les mêmes noms au
  build. Un fichier manquant donne une carte sans image, **jamais** l'adresse
  d'origine. Le lecteur YouTube reste chargé au seul clic (ADR 0036).
- **Un visiteur est une requête humaine.** Ni robot déclaré, ni requête sans
  langue, ni préchargement, ni erreur. Le critère se lit dans les mesures déjà
  écrites et s'applique donc aussi à l'historique. Les sondes de failles
  (`/.env`, `/wp-login.php`, `/phpinfo`…) quittent la liste des liens morts
  pour un simple total.
- **L'éditeur reste anonyme**, comme la LCEN le permet aux éditeurs non
  professionnels : son identité est connue de l'hébergeur, la page donne une
  adresse de contact.

## Conséquences

- Positives : chaque phrase de `/mentions-legales` est tenue par du code
  testé ; la page d'audience montre des personnes (le pic du premier carrousel
  Instagram, 187 visiteurs le 2026-10-14, devient lisible).
- Négatives : 5,8 Mo de vignettes versionnées, et une étape de plus dans la
  chaîne de venus (récupérer la vignette avant de publier). Un robot qui
  annonce une langue passe toujours pour un humain : la mesure reste une
  estimation.
- Notes : les notifications Matrix des signalements gardent nom et e-mail
  sans limite — hors de portée de la purge. Toute nouvelle donnée mesurée,
  ressource tierce ou durée doit changer la page dans la même PR.
