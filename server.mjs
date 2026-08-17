/**
 * server.mjs — point d'entrée de la PRODUCTION (`npm start`).
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * `@astrojs/node` (v11) ne compresse rien, et l'hébergement Infomaniak n'offre
 * aucun réglage de compression : il exécute simplement `npm start`. Résultat
 * mesuré le 2026-08-16 sur https://unebonnere.co/ — aucun `content-encoding`,
 * et **2599 Ko envoyés à chaque visiteur** là où 199 suffiraient. Sur un mobile
 * en 4G moyenne, cela fait 13 secondes de transfert au lieu d'une.
 *
 * POURQUOI SANS DÉPENDANCE
 * ------------------------
 * La commande de build de l'hébergeur est `npm ci --omit=dev` : ajouter
 * `express` + `compression` obligerait à les faire passer en `dependencies`,
 * donc à alourdir l'installation de production et la surface à auditer. Tout
 * ici n'utilise que `node:`.
 *
 * POURQUOI IL EST SI COURT
 * ------------------------
 * Tout ce qui a une logique vit dans `src/server/` et s'y teste avec un faux
 * gestionnaire. Ne reste ici que ce qui ne peut PAS être testé sans un build :
 * l'import de `dist/server/entry.mjs` et l'ouverture du port. La première
 * version mélangeait les deux, et n'avait par conséquent aucun test — sur le
 * fichier qui sert chaque visiteur.
 *
 * CE QUI N'EST VOLONTAIREMENT PAS IMPLÉMENTÉ
 * ------------------------------------------
 * Les requêtes `Range` : `dist/client` ne contient aucun média (vérifié le
 * 2026-08-17 — audio et vidéo sont hébergés chez Acast et YouTube). Les
 * réintroduire coûterait du code non exercé. À reconsidérer le jour où un
 * fichier audio serait servi depuis le site.
 */
import { resolve } from 'node:path';

// Export NOMMÉ : en mode `middleware`, l'entrée expose
// `{ handler, options, startServer }` — il n'y a pas d'export par défaut.
import { handler } from './dist/server/entry.mjs';
import { creerServeur, fermerProprement } from './src/server/serveur.mjs';

const PORT = Number(process.env.PORT) || 3000;
const HOTE = process.env.HOST || '0.0.0.0';

const serveur = fermerProprement(creerServeur(handler, resolve('./dist/client')));

serveur.listen(PORT, HOTE, () => {
  console.log(`Reco — serveur avec compression sur http://${HOTE}:${PORT}`);
});
