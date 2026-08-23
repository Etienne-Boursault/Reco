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

import { creerServeurMaintenance } from './src/server/maintenance.mjs';
import { creerServeur, fermerProprement } from './src/server/serveur.mjs';

const PORT = Number(process.env.PORT) || 3000;
const HOTE = process.env.HOST || '0.0.0.0';

/**
 * Charge l'entrée construite, ou rend `null` si elle est inutilisable.
 *
 * L'import est DYNAMIQUE et gardé. En statique — `import { handler } from
 * './dist/server/entry.mjs'` en tête de fichier — l'absence du fichier
 * empêche le module de se charger : le processus meurt avant même d'ouvrir le
 * port, et le site est mort, pas dégradé. C'est ce qui s'est produit le
 * 2026-08-21 pendant quarante minutes, une construction ayant échoué après
 * qu'Astro a vidé `dist/`.
 *
 * Export NOMMÉ : en mode `middleware`, l'entrée expose `{ handler, options,
 * startServer }` — il n'y a pas d'export par défaut.
 */
async function chargerGestionnaire() {
  try {
    const entree = await import('./dist/server/entry.mjs');
    if (typeof entree.handler !== 'function') {
      console.error('[server] dist/server/entry.mjs n’exporte pas `handler`.');
      return null;
    }
    return entree.handler;
  } catch (err) {
    console.error('[server] dist/server/entry.mjs illisible :', err?.message ?? err);
    return null;
  }
}

const handler = await chargerGestionnaire();

// Le serveur s'ouvre dans les deux cas. Répondre « le site revient » vaut
// mieux que ne pas répondre : le visiteur comprend, et le 503 dit aux moteurs
// de repasser au lieu de désindexer.
const serveur = fermerProprement(
  handler
    ? creerServeur(handler, resolve('./dist/client'))
    : creerServeurMaintenance(),
);

serveur.listen(PORT, HOTE, () => {
  console.log(
    handler
      ? `Reco — serveur avec compression sur http://${HOTE}:${PORT}`
      : `Reco — MODE DÉGRADÉ sur http://${HOTE}:${PORT} : la construction a `
        + 'échoué ou est incomplète. Les visiteurs voient une page d’attente '
        + '(503). Relancer une construction corrige la situation.',
  );
});
