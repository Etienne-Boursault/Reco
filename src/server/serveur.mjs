/**
 * Assemblage du serveur de production : statique d'abord, Astro ensuite.
 *
 * Ce module ne connaît PAS Astro — il reçoit un gestionnaire en paramètre.
 * C'est ce qui le rend testable : `server.mjs`, qui importe le gestionnaire
 * réel depuis `dist/server/entry.mjs`, n'existe qu'après un build, alors que
 * ce fichier-ci s'éprouve avec un faux gestionnaire en quelques millisecondes.
 */
import { readFileSync } from 'node:fs';
import http from 'node:http';
import { join } from 'node:path';

import { hoteDe, mesurerVisite, sourcesDe } from '../lib/audience/mesure.mjs';
import { envelopper } from './compression.mjs';
import { METHODES_STATIQUES, fichierPour, servirFichier } from './fichiers.mjs';

/** Le domaine public et les sources connues — voir `lib/audience/mesure.mjs`. */
const HOTE_DU_SITE = hoteDe(process.env.SITE_URL);
const SOURCES_CONNUES = sourcesDe(process.env.RECO_SOURCES);

/**
 * Traite une requête : fichier construit si l'URL en désigne un, sinon Astro.
 *
 * L'ordre n'est pas indifférent. Le statique passe en premier parce qu'il
 * couvre l'écrasante majorité des requêtes et coûte le moins ; et parce qu'une
 * route à la demande ne doit jamais masquer un fichier réellement construit.
 */
export function traiter(handler, racine, req, res, mesurer = mesurerVisite) {
  // La mesure se pose AVANT tout aiguillage, pour couvrir aussi bien une page
  // servie depuis le disque qu'une route à la demande ou un 404. Elle
  // n'écrit rien tout de suite : elle s'abonne à la fin de la réponse, quand
  // le statut et le poids sont connus. Voir `src/lib/audience/mesure.mjs`.
  //
  // Injectable pour que les tests du serveur n'écrivent pas sur le disque.
  mesurer?.(req, res, { hoteDuSite: HOTE_DU_SITE, sourcesConnues: SOURCES_CONNUES });

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

  return handler(req, envelopper(req, res), () => repondre404(res, racine));
}

/**
 * Le dernier recours : la page 404 construite, ou du texte si elle manque.
 *
 * Ce repli servait seize octets de `text/plain` — « Page introuvable » — sans
 * navigation ni charte. Sur un catalogue de plus de mille pages indexées, dont
 * les fiches d'œuvre changent d'identifiant après une fusion de doublons, un
 * lien périmé est un cas ordinaire, pas une bizarrerie. Le visiteur tombait
 * dans un cul-de-sac.
 *
 * `dist/client/404.html` vient de `src/pages/404.astro` : même charte, mêmes
 * sorties que le reste du site. Le texte brut reste en dernier recours, pour
 * le cas où la page n'aurait pas été construite — un repli doit toujours avoir
 * un repli.
 */
export function repondre404(res, racine, { lire = readFileSync } = {}) {
  try {
    const page = lire(join(racine, '404.html'));
    res.writeHead(404, {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Length': page.length,
    });
    res.end(page);
    return;
  } catch {
    // Page absente ou illisible : on ne laisse pas remonter, une erreur ici
    // arrêterait le processus — donc tout le site — pour une page manquante.
  }
  const corps = 'Page introuvable';
  res.writeHead(404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': Buffer.byteLength(corps),
  });
  res.end(corps);
}

/**
 * Crée le serveur HTTP sans l'ouvrir : l'appelant décide quand écouter.
 *
 * `mesurer` est injectable pour la même raison que dans `traiter` : la mesure
 * par défaut ÉCRIT SUR LE DISQUE, sous `tools/output/audience/`. Les tests du
 * serveur passaient par ici sans la remplacer, et chaque exécution de la suite
 * ajoutait de vraies lignes au corpus local — `/nulle-part`,
 * `/../../../etc/passwd` et les autres chemins d'essai se retrouvaient dans le
 * tableau de bord. Le piège est ancien dans ce dépôt : un chemin résolu au
 * moment de l'appel finit toujours par pointer sur le vrai dossier.
 */
export function creerServeur(handler, racine, mesurer = mesurerVisite) {
  return http.createServer((req, res) => traiter(handler, racine, req, res, mesurer));
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
