/**
 * Le branchement : mesurer une visite sans jamais gêner la réponse.
 *
 * QUAND MESURER
 * -------------
 * À la FIN de la réponse, pas au début. Le statut, la durée et le poids ne
 * sont connus qu'une fois la dernière octet parti — et une page servie en 404
 * ou en 503 n'est pas une page vue comme les autres.
 *
 * `res.once('finish')` se déclenche quand la réponse est écrite. Si le
 * visiteur coupe avant, l'événement `close` arrive sans `finish` : la visite
 * n'est pas comptée, ce qui est le bon comportement — elle n'a pas eu lieu.
 *
 * PRIORITÉ ABSOLUE : NE RIEN CASSER
 * ---------------------------------
 * Ce code est sur le chemin de chaque requête. Tout y est enveloppé : une
 * erreur de mesure ne doit jamais empêcher une page de s'afficher. En cas de
 * doute, on ne compte pas.
 */
import { estUnePage, evenementDeVisite } from './derive.mjs';
import { enregistrer } from './storage.mjs';

/**
 * L'adresse du visiteur, pour la seule empreinte quotidienne.
 *
 * On lit le DERNIER saut de `x-forwarded-for`, pas le premier : le premier est
 * écrit par le client et donc forgeable, le dernier est posé par notre propre
 * intermédiaire. Cette règle vient de `src/lib/http/resolveClientIp.ts`, qu'on
 * ne peut pas importer ici — ce module est chargé par `server.mjs`, en pur
 * JavaScript, avant qu'aucun TypeScript ne soit transpilé.
 *
 * L'adresse ne sort jamais de cette fonction autrement que condensée.
 */
export function adresseCliente(req) {
  const suivi = req.headers?.['x-forwarded-for'];
  if (typeof suivi === 'string' && suivi.trim()) {
    const sauts = suivi.split(',').map((s) => s.trim()).filter(Boolean);
    if (sauts.length) return sauts[sauts.length - 1];
  }
  return req.socket?.remoteAddress ?? null;
}

/**
 * À quelle source rattacher la visite.
 *
 * Le premier segment du chemin porte le podcast (`/un-bon-moment/…`). Les
 * pages communes — accueil, à propos, manifeste — n'en ont pas : elles vont
 * dans `_site`, un nom qui ne peut pas entrer en collision avec un slug de
 * source puisqu'il commence par un souligné.
 */
/**
 * Le nom d'hôte du domaine public, tiré de `SITE_URL`.
 *
 * Sert à distinguer une arrivée depuis l'extérieur d'une navigation interne.
 * Rend `null` sur une valeur absente ou illisible : sans lui, toutes les pages
 * internes compteraient comme des provenances — un site qui se référencerait
 * lui-même.
 */
export function hoteDe(siteUrl) {
  if (!siteUrl) return null;
  try {
    return new URL(siteUrl).hostname || null;
  } catch {
    return null;
  }
}

/**
 * Les slugs de source connus, depuis une liste séparée par des virgules.
 *
 * Rend `null` quand rien n'est déclaré — tout sera alors rangé dans `_site`,
 * ce qui reste juste, seulement moins précis.
 */
export function sourcesDe(csv) {
  if (!csv) return null;
  const slugs = csv.split(',').map((s) => s.trim()).filter(Boolean);
  return slugs.length ? new Set(slugs) : null;
}

/**
 * Sous quelle source ranger cette visite.
 *
 * Une source doit être DÉCLARÉE (`RECO_SOURCES`) pour exister : sans liste, le
 * premier segment d'URL n'est qu'une chaîne venue du dehors, et lui faire
 * confiance revenait à créer un dossier par racine visitée. Tout ce qui n'est
 * pas reconnu va dans `_site` — ce qui reste juste, seulement moins précis.
 */
export function sourceDuChemin(chemin, sourcesConnues) {
  const segment = (chemin || '/').split('?')[0].split('/')[1] ?? '';
  if (!segment) return '_site';
  if (!sourcesConnues || !sourcesConnues.has(segment)) return '_site';
  return /^[a-z0-9_-]{1,128}$/.test(segment) ? segment : '_site';
}

/**
 * Pose la mesure sur une requête. Rend une fonction d'annulation (tests).
 *
 * `options.sel` vient de `RECO_AUDIENCE_SALT`. Sans lui, l'empreinte de
 * visiteur vaut `null` : le reste est compté normalement, on perd seulement
 * la distinction entre pages vues et visiteurs. C'est un choix — un sel
 * absent ne doit pas faire taire toute la mesure.
 */
export function mesurerVisite(req, res, options = {}) {
  const {
    cwd = process.cwd(),
    sel = process.env.RECO_AUDIENCE_SALT ?? null,
    hoteDuSite = null,
    sourcesConnues = null,
    ecrire = enregistrer,
    horloge = Date.now,
  } = options;

  const debut = horloge();
  const chemin = req.url || '/';

  if (!estUnePage(chemin, req.method)) return () => {};

  const surFin = () => {
    try {
      const evenement = evenementDeVisite({
        chemin,
        methode: req.method,
        statut: res.statusCode,
        entetes: req.headers ?? {},
        ip: adresseCliente(req),
        sel,
        hoteDuSite,
        dureeMs: horloge() - debut,
        maintenant: new Date(),
      });
      ecrire(evenement, sourceDuChemin(chemin, sourcesConnues), cwd);
    } catch {
      // Mesurer est secondaire. Une page servie vaut mieux qu'une statistique.
    }
  };

  // `res` n'est pas toujours un vrai `ServerResponse` : les tests du serveur
  // passent un double minimal, et une future couche pourrait faire de même.
  // Sans cette garde, mesurer ferait échouer la requête — l'inverse exact de
  // ce que ce module promet.
  if (typeof res.once !== 'function') return () => {};

  res.once('finish', surFin);
  return () => res.off?.('finish', surFin);
}
