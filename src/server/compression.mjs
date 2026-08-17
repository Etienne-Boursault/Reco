/**
 * Compression gzip à la volée des réponses produites par le gestionnaire Astro.
 *
 * POURQUOI UNE ENVELOPPE PLUTÔT QU'UN RÉGLAGE
 * -------------------------------------------
 * `@astrojs/node` (v11) ne compresse rien et l'hébergeur n'offre aucun réglage :
 * il lance `npm start`, point. La seule prise possible est donc d'envelopper
 * l'objet `res` avant de le confier au gestionnaire.
 *
 * LA DIFFICULTÉ, ET LE PIÈGE QUI A COÛTÉ UNE VERSION
 * --------------------------------------------------
 * On ne peut pas décider de compresser avant de connaître le `Content-Type` —
 * qui n'est connu qu'au `writeHead`. La première version interceptait donc
 * `writeHead` et lisait `res.getHeader('Content-Type')`.
 *
 * C'était inerte. Le cœur d'Astro écrit ainsi (`core/app/node.js`) :
 *
 *     destination.writeHead(status, createOutgoingHttpHeaders(headers))
 *
 * Les en-têtes sont passés EN ARGUMENT, jamais posés par `setHeader`. Au
 * moment de l'interception, `getHeader('Content-Type')` renvoyait donc
 * `undefined`, la condition était toujours fausse, et pas un octet n'était
 * compressé. Un fichier écrit pour compresser qui ne compressait rien, sans le
 * moindre signal.
 *
 * D'où `normaliserEntetes` : on lit les en-têtes LÀ OÙ ILS SONT — dans les
 * arguments — avant de retomber sur `getHeader`.
 *
 * Corollaire important : les en-têtes passés en argument ÉCRASENT ceux posés
 * par `setHeader`. Il ne suffit donc pas d'appeler `res.removeHeader(...)`
 * pour retirer le `Content-Length` du contenu en clair ; il faut le retirer de
 * l'objet transmis, puis retransmettre cet objet.
 */
import { createGzip } from 'node:zlib';

/**
 * Types qui gagnent à être compressés. Images, vidéos et polices modernes le
 * sont DÉJÀ : les repasser au gzip coûte du processeur pour un gain nul, voire
 * négatif.
 */
export const COMPRESSIBLE =
  /^(?:text\/|application\/(?:json|javascript|xml|rss\+xml|manifest\+json)|image\/svg\+xml)/;

/**
 * En deçà, l'en-tête `Content-Encoding` pèse plus que ce que la compression
 * fait gagner.
 */
export const TAILLE_MINI = 1024;

/**
 * Statuts dont la réponse N'A PAS de corps. Y poser un flux gzip produirait
 * les ~20 octets d'un flux vide sur une réponse qui doit en faire zéro, ce que
 * les clients interprètent comme une réponse malformée.
 */
const SANS_CORPS = new Set([204, 205, 304]);

/**
 * Le client accepte-t-il gzip ?
 *
 * La limite de mot est ce qui distingue `gzip` de `notgzip` : sans elle, on
 * compresserait pour un client qui ne sait pas décompresser.
 */
export const accepteGzip = (req) =>
  /\bgzip\b/.test(req.headers?.['accept-encoding'] || '');

/**
 * Ramène les arguments de `writeHead` à un objet d'en-têtes MODIFIABLE.
 *
 * `writeHead` accepte quatre formes : `(code)`, `(code, entetes)`,
 * `(code, message)` et `(code, message, entetes)` — les en-têtes pouvant eux
 * -mêmes être un objet, un tableau plat `[k, v, k, v]` ou un tableau de paires.
 * Tout est ramené ici à un objet, copié pour que l'appelant puisse le modifier
 * sans effet de bord sur l'objet d'origine.
 */
export function normaliserEntetes(reste) {
  let message;
  let brut = reste[0];
  if (typeof brut === 'string') {
    message = brut;
    brut = reste[1];
  }
  const entetes = {};
  if (Array.isArray(brut)) {
    if (Array.isArray(brut[0])) {
      for (const [cle, valeur] of brut) entetes[cle] = valeur;
    } else {
      for (let i = 0; i + 1 < brut.length; i += 2) entetes[brut[i]] = brut[i + 1];
    }
  } else if (brut && typeof brut === 'object') {
    Object.assign(entetes, brut);
  }
  return { message, entetes };
}

/** Lit un en-tête sans se soucier de la casse (HTTP l'ignore, pas JavaScript). */
export function lireEntete(entetes, nom) {
  const cible = nom.toLowerCase();
  for (const [cle, valeur] of Object.entries(entetes)) {
    if (cle.toLowerCase() === cible) return valeur;
  }
  return undefined;
}

/** Retire un en-tête quelle que soit la casse employée pour le poser. */
export function retirerEntete(entetes, nom) {
  const cible = nom.toLowerCase();
  for (const cle of Object.keys(entetes)) {
    if (cle.toLowerCase() === cible) delete entetes[cle];
  }
}

/**
 * Ajoute `Accept-Encoding` à un `Vary` existant sans écraser ce qu'il portait.
 *
 * Écraser un `Vary: Cookie` ferait servir à tous la réponse mise en cache pour
 * un seul — une fuite entre visiteurs, pas seulement une gêne.
 */
export function fusionnerVary(actuel) {
  const parts = String(actuel ?? '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean);
  if (!parts.some((p) => p.toLowerCase() === 'accept-encoding')) {
    parts.push('Accept-Encoding');
  }
  return parts.join(', ');
}

/** Décide, à partir des en-têtes effectifs, s'il faut compresser. */
function fautCompresser(req, res, code, entetes) {
  const type = String(lireEntete(entetes, 'content-type') ?? res.getHeader('content-type') ?? '');
  const encode = lireEntete(entetes, 'content-encoding') ?? res.getHeader('content-encoding');
  const brut = lireEntete(entetes, 'content-length') ?? res.getHeader('content-length');
  const longueur = brut === undefined ? null : Number(brut);

  if (!COMPRESSIBLE.test(type)) return false;
  if (encode) return false;                       // déjà encodé par plus haut
  if (SANS_CORPS.has(code)) return false;
  if (req.method === 'HEAD') return false;        // en-têtes seuls, pas de corps
  // Longueur inconnue → on compresse : c'est le cas des pages rendues en flux,
  // justement les plus lourdes.
  if (longueur !== null && Number.isFinite(longueur) && longueur < TAILLE_MINI) return false;
  return true;
}

/**
 * Enveloppe `res` pour compresser ce que le gestionnaire y écrira.
 *
 * Renvoie `res` lui-même (muté) : l'appelant passe le résultat au gestionnaire.
 *
 * `creerCompresseur` n'est injectable que pour éprouver la contre-pression et
 * la capture d'erreur — deux comportements qu'on ne peut pas déclencher depuis
 * l'extérieur, et dont l'absence ne se remarquerait qu'en production, sous la
 * forme d'un processus qui s'arrête.
 */
export function envelopper(req, res, {
  creerCompresseur = () => createGzip({ level: 6 }),
} = {}) {
  if (!accepteGzip(req)) return res;

  const writeHeadOriginal = res.writeHead.bind(res);
  const writeOriginal = res.write.bind(res);
  const endOriginal = res.end.bind(res);
  let gz = null;

  res.writeHead = (code, ...reste) => {
    const { message, entetes } = normaliserEntetes(reste);

    if (fautCompresser(req, res, code, entetes)) {
      // Le `Content-Length` annonçait la taille EN CLAIR. Le laisser ferait
      // tronquer la réponse côté client — le corps compressé est plus court
      // que ce qui est annoncé, et le navigateur attend indéfiniment la suite.
      retirerEntete(entetes, 'content-length');
      res.removeHeader('Content-Length');

      const varyExistant = lireEntete(entetes, 'vary') ?? res.getHeader('vary');
      retirerEntete(entetes, 'vary');
      entetes.Vary = fusionnerVary(varyExistant);
      entetes['Content-Encoding'] = 'gzip';

      gz = creerCompresseur();
      // Contre-pression : sans la pause, un gros document se recopie
      // intégralement en mémoire quand le client lit lentement.
      gz.on('data', (morceau) => {
        if (writeOriginal(morceau) === false) gz.pause();
      });
      res.on('drain', () => gz.resume());
      gz.on('end', () => endOriginal());
      // Sans écouteur d'erreur, un flux gzip en échec lève un événement
      // `error` non capté — ce qui TUE le processus, donc le site entier.
      gz.on('error', () => res.destroy());
      // Client parti en cours de route : on libère le compresseur.
      res.on('close', () => gz?.destroy());
    }

    return message === undefined
      ? writeHeadOriginal(code, entetes)
      : writeHeadOriginal(code, message, entetes);
  };

  res.write = (morceau, ...suite) =>
    (gz ? gz.write(morceau, ...suite) : writeOriginal(morceau, ...suite));

  res.end = (morceau, encodage, rappel) => {
    // `end` accepte le rappel en 1re ou 2e position. Sans ce démêlage, une
    // fonction finissait passée à gzip comme si c'était un corps.
    if (typeof morceau === 'function') {
      rappel = morceau;
      morceau = undefined;
      encodage = undefined;
    } else if (typeof encodage === 'function') {
      rappel = encodage;
      encodage = undefined;
    }
    if (!gz) return endOriginal(morceau, encodage, rappel);
    if (rappel) res.once('finish', rappel);
    if (morceau) gz.end(morceau, encodage);
    else gz.end();
    return res;
  };

  return res;
}
