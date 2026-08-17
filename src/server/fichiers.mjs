/**
 * Service des fichiers statiques de `dist/client`.
 *
 * En mode `middleware`, Astro ne sert plus rien lui-même : il fournit un
 * gestionnaire pour les routes à la demande, et c'est à nous de servir le site
 * construit. Ce module reprend donc ce que faisait l'adaptateur en mode
 * `standalone` — résolution du chemin, types MIME, cache, requêtes
 * conditionnelles — en y ajoutant la compression, seule raison de cette
 * reprise en main.
 */
import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, sep } from 'node:path';
import { createGzip } from 'node:zlib';

import { COMPRESSIBLE, TAILLE_MINI, accepteGzip } from './compression.mjs';

export const TYPES = new Map(Object.entries({
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.xml': 'application/xml; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
}));

/** Seules ces méthodes se servent depuis le disque ; le reste part au
 *  gestionnaire, qui saura répondre 405 ou traiter la route. */
export const METHODES_STATIQUES = new Set(['GET', 'HEAD']);

/**
 * Résout une URL vers un fichier sous `racine`, ou `null`.
 *
 * La normalisation SUIVIE de la vérification du préfixe est la garde contre la
 * traversée de répertoire. L'ordre compte : vérifier avant de normaliser
 * laisserait passer `/a/../../etc/passwd`, dont le préfixe est correct tant
 * qu'on ne l'a pas réduit.
 */
export function fichierPour(racine, urlPath, { stat = statSync } = {}) {
  let rel;
  try {
    rel = decodeURIComponent(String(urlPath).split('?')[0]);
  } catch {
    return null;                       // séquence de pourcentage mal formée
  }
  // Un octet nul tronque le chemin dans les appels système sous-jacents :
  // « /public/logo.png\0.txt » deviendrait « /public/logo.png ». Node le
  // refuse déjà, mais on ne s'appuie pas sur ce refus.
  if (rel.includes('\0')) return null;

  const abs = normalize(join(racine, rel));
  if (abs !== racine && !abs.startsWith(racine + sep)) return null;

  for (const candidat of [abs, join(abs, 'index.html')]) {
    try {
      // `throwIfNoEntry: false` renvoie `undefined` au lieu de lever quand le
      // fichier n'existe pas. Un seul appel système suffit donc, là où le
      // couple `existsSync` + `statSync` en faisait deux — et ouvrait une
      // course : le fichier pouvait disparaître entre les deux, et le
      // `statSync` levait alors sur un chemin déclaré existant.
      if (stat(candidat, { throwIfNoEntry: false })?.isFile()) return candidat;
    } catch {
      // Reste les erreurs que `throwIfNoEntry` ne couvre pas — au premier chef
      // ENOTDIR, que produit `/index.html/en-plus` : un segment ajouté après un
      // fichier. Sans ce `catch`, cette URL banale ferait remonter une
      // exception jusqu'au serveur.
      //
      // La sonde est injectable parce que ce cas dépend du SYSTÈME : Linux
      // lève ENOTDIR, tandis que Windows ramène tout à « absent » et ne lève
      // rien. Un test qui s'en remettrait au système réel ne couvrirait donc
      // cette ligne que sur une plateforme sur deux.
      return null;
    }
  }
  return null;
}

/**
 * Empreinte d'un fichier, pour les requêtes conditionnelles.
 *
 * Faible (`W/`) et dérivée de la taille et de la date : deux contenus
 * différents de même taille ET de même date sont indiscernables, ce qui
 * n'arrive pas pour un site reconstruit. Une empreinte forte imposerait de
 * lire tout le fichier à chaque requête — le remède serait pire.
 */
export function empreinte(stat) {
  return `W/"${stat.size.toString(16)}-${Math.floor(stat.mtimeMs).toString(16)}"`;
}

/**
 * Politique de cache : un an pour les fichiers empreintés, revalidation pour
 * le reste.
 *
 * Les fichiers de `_astro/` portent une empreinte dans leur NOM : leur contenu
 * ne peut pas changer sans que l'URL change. Un an est donc sûr — et c'est ce
 * qui rend les visites suivantes quasi instantanées.
 */
export function politiqueCache(chemin) {
  return chemin.includes(`${sep}_astro${sep}`)
    ? 'public, max-age=31536000, immutable'
    : 'public, max-age=0, must-revalidate';
}

/**
 * Sert un fichier : requête conditionnelle, cache, compression.
 *
 * Les deux fabriques sont injectables pour une seule raison : les gestionnaires
 * d'erreur ci-dessous sont ce qui empêche une lecture en échec de TUER le
 * processus, et une protection jamais exercée n'est pas une protection. Les
 * provoquer autrement demanderait de faire disparaître un fichier au milieu de
 * sa propre lecture.
 */
export function servirFichier(req, res, chemin, {
  creerFlux = createReadStream,
  creerCompresseur = () => createGzip({ level: 6 }),
} = {}) {
  const type = TYPES.get(extname(chemin).toLowerCase()) || 'application/octet-stream';
  const stat = statSync(chemin);
  const etag = empreinte(stat);
  const compressible = COMPRESSIBLE.test(type);

  const entetes = {
    'Content-Type': type,
    'Cache-Control': politiqueCache(chemin),
    ETag: etag,
    'Last-Modified': new Date(stat.mtimeMs).toUTCString(),
  };
  // `Vary` est OBLIGATOIRE dès qu'on négocie : sans lui, un cache
  // intermédiaire servirait la version compressée à un client qui ne l'accepte
  // pas, et lui afficherait des octets illisibles.
  if (compressible) entetes.Vary = 'Accept-Encoding';

  // Requête conditionnelle : le client a déjà le fichier. Répondre 304 évite
  // de renvoyer le corps — c'est ce qui rend les visites suivantes légères, et
  // ce que l'adaptateur `standalone` faisait avant cette reprise en main.
  if (req.headers['if-none-match'] === etag) {
    res.writeHead(304, {
      ETag: etag,
      'Cache-Control': entetes['Cache-Control'],
      ...(compressible ? { Vary: 'Accept-Encoding' } : {}),
    });
    return res.end();
  }

  const compresser = accepteGzip(req) && compressible && stat.size >= TAILLE_MINI;

  if (!compresser) entetes['Content-Length'] = stat.size;
  // Sinon : pas de `Content-Length`, la taille compressée n'étant connue qu'à
  // la fin. Le corps part en `Transfer-Encoding: chunked`, que Node gère seul.
  else entetes['Content-Encoding'] = 'gzip';

  res.writeHead(200, entetes);
  if (req.method === 'HEAD') return res.end();

  const flux = creerFlux(chemin);
  // SANS cet écouteur, une erreur de lecture (fichier supprimé pendant un
  // déploiement, disque en défaut) lève un événement `error` non capté qui
  // TERMINE le processus — et donc met le site entier hors ligne. `pipe` ne
  // propage pas les erreurs : il faut les prendre ici.
  flux.on('error', () => res.destroy());

  if (!compresser) return flux.pipe(res);
  const gz = creerCompresseur();
  gz.on('error', () => res.destroy());
  return flux.pipe(gz).pipe(res);
}
