/**
 * Assemblage du serveur de production : statique d'abord, Astro ensuite.
 *
 * Ce module ne connaît PAS Astro — il reçoit un gestionnaire en paramètre.
 * C'est ce qui le rend testable : `server.mjs`, qui importe le gestionnaire
 * réel depuis `dist/server/entry.mjs`, n'existe qu'après un build, alors que
 * ce fichier-ci s'éprouve avec un faux gestionnaire en quelques millisecondes.
 */
import http from 'node:http';

import { envelopper } from './compression.mjs';
import { METHODES_STATIQUES, fichierPour, servirFichier } from './fichiers.mjs';

/**
 * Traite une requête : fichier construit si l'URL en désigne un, sinon Astro.
 *
 * L'ordre n'est pas indifférent. Le statique passe en premier parce qu'il
 * couvre l'écrasante majorité des requêtes et coûte le moins ; et parce qu'une
 * route à la demande ne doit jamais masquer un fichier réellement construit.
 */
export function traiter(handler, racine, req, res) {
  // Seuls GET et HEAD se servent depuis le disque : un POST vers `/index.html`
  // doit atteindre le gestionnaire, qui répondra 405, et non recevoir la page
  // avec un 200 qui laisserait croire que l'envoi a été pris en compte.
  const chemin = METHODES_STATIQUES.has(req.method)
    ? fichierPour(racine, req.url || '/')
    : null;
  // `servirFichier` rend `false` quand le fichier a disparu entre la
  // résolution du chemin et sa lecture — la fenêtre qu'ouvre un redéploiement.
  // On retombe alors sur le gestionnaire, qui répondra 404 ; laisser remonter
  // l'exception arrêterait le processus, donc tout le site.
  if (chemin && servirFichier(req, res, chemin)) return undefined;

  return handler(req, envelopper(req, res), () => {
    const corps = 'Page introuvable';
    res.writeHead(404, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Content-Length': Buffer.byteLength(corps),
    });
    res.end(corps);
  });
}

/** Crée le serveur HTTP sans l'ouvrir : l'appelant décide quand écouter. */
export function creerServeur(handler, racine) {
  return http.createServer((req, res) => traiter(handler, racine, req, res));
}

/**
 * Ferme proprement le serveur sur SIGTERM/SIGINT.
 *
 * L'hébergeur envoie SIGTERM à chaque redéploiement. Sans cette fermeture, les
 * requêtes en cours sont coupées net : le visiteur voit une page à moitié
 * chargée, sans erreur exploitable. `close` laisse finir ce qui est commencé
 * et refuse les nouvelles connexions.
 */
export function fermerProprement(serveur, { signaux = ['SIGTERM', 'SIGINT'], sortie = process.exit } = {}) {
  for (const signal of signaux) {
    process.once(signal, () => {
      serveur.close(() => sortie(0));
    });
  }
  return serveur;
}
