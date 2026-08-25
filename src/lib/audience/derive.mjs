/**
 * Ce qu'on retient d'une visite — et surtout ce qu'on jette.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Infomaniak ne fournit aucune statistique pour un site Node.js : il sert ses
 * requêtes lui-même, le serveur web mutualisé n'en voit rien passer. Or le
 * site est son propre serveur — chaque requête traverse `server.mjs`. Compter
 * ici est la seule façon de savoir qui vient, et la seule qui n'ajoute aucun
 * tiers.
 *
 * LA RÈGLE
 * --------
 * Le manifeste du projet dit : « Aucun tracker tiers. Aucun cookie marketing.
 * Aucun cookie analytique. » Ce module s'y tient, et va plus loin : chaque
 * en-tête est réduit à une CATÉGORIE avant d'être écrit, jamais conservé tel
 * quel. Un agent utilisateur complet, un référent complet, une IP : ce sont
 * des empreintes. « mobile », « google.com », un condensat salé du jour : ce
 * n'en sont pas.
 *
 * CE QU'ON NE FAIT PAS
 * --------------------
 * Pas de reconstitution de parcours. Relier deux pages d'un même visiteur est
 * bien plus identifiant que leur somme, pour un gain faible — arbitrage de
 * l'éditeur, 2026-08-25.
 *
 * Pas de poids de réponse non plus. `server.mjs` compresse, et la compression
 * retire `Content-Length` — il annonçait la taille EN CLAIR. Le champ aurait
 * donc été vide pour toutes les pages HTML, c'est-à-dire précisément celles
 * qui comptent. Capter la taille compressée demanderait de modifier la couche
 * de compression, du code tenu à 100 % de couverture, pour une mesure que
 * l'éditeur a lui-même classée secondaire. Un champ qui prétend mesurer sans
 * mesurer vaut moins que pas de champ.
 */
import { createHash } from 'node:crypto';
import { paysDeIP } from './geoip.mjs';

/**
 * Ce qui n'est pas une page : on ne compte pas les feuilles de style.
 *
 * Sans ce filtre, une seule visite écrirait trente lignes — une par ressource
 * — et les chiffres ne voudraient plus rien dire.
 */
const EXT_IGNOREES = new Set([
  '.css', '.js', '.mjs', '.map', '.svg', '.png', '.jpg', '.jpeg', '.webp',
  '.avif', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.xml', '.json', '.txt',
]);

/** Chemins techniques : utiles au fonctionnement, pas à la fréquentation. */
const PREFIXES_IGNORES = ['/_astro/', '/api/', '/og/', '/.well-known/'];

/**
 * Pages d'administration : consultées par l'éditeur, pas par le public.
 *
 * Chemins EXACTS, pas des préfixes — `/audience` ne doit pas écarter
 * `/audiences-publiques`, qui serait une page comme une autre.
 *
 * Sans cette garde, `/audience` est arrivée en tête des pages les plus
 * consultées le jour même de sa mise en service, et ses appels sans clé — qui
 * répondent 404 — ont rempli la section des liens morts. Un tableau de bord
 * qui se compte lui-même dégrade ses chiffres à chaque consultation.
 */
const CHEMINS_IGNORES = new Set(['/audience']);

/**
 * Marqueurs de robots.
 *
 * La liste est courte et le restera : elle sert à SÉPARER, pas à identifier.
 * Un robot inconnu comptera comme un humain — mieux vaut ça qu'une liste
 * interminable qui finirait par distinguer les navigateurs entre eux.
 */
const MARQUEURS_ROBOT = [
  'bot', 'crawl', 'spider', 'slurp', 'facebookexternalhit', 'preview',
  'monitor', 'curl', 'wget', 'python-requests', 'headless', 'lighthouse',
];

/** Marqueurs de mobile. Deux catégories, jamais le modèle : voir plus haut. */
const MARQUEURS_MOBILE = ['mobile', 'android', 'iphone', 'ipad', 'ipod'];

/** Une requête vaut-elle d'être comptée comme page vue ? */
export function estUnePage(chemin, methode = 'GET') {
  if (methode !== 'GET') return false;
  if (typeof chemin !== 'string' || !chemin.startsWith('/')) return false;
  const sansQuery = chemin.split('?')[0];
  if (PREFIXES_IGNORES.some((p) => sansQuery.startsWith(p))) return false;
  // `trailingSlash: 'ignore'` : `/audience` et `/audience/` sont la même page.
  const nu = sansQuery.length > 1 && sansQuery.endsWith('/')
    ? sansQuery.slice(0, -1)
    : sansQuery;
  if (CHEMINS_IGNORES.has(nu)) return false;
  const point = sansQuery.lastIndexOf('.');
  if (point > sansQuery.lastIndexOf('/')) {
    return !EXT_IGNOREES.has(sansQuery.slice(point).toLowerCase());
  }
  return true;
}

/** Le chemin, sans la chaîne de requête — elle peut porter n'importe quoi. */
export function cheminSeul(url) {
  if (typeof url !== 'string') return '/';
  const chemin = url.split('?')[0].split('#')[0];
  return chemin.startsWith('/') ? chemin.slice(0, 512) : '/';
}

/**
 * Le domaine du référent, jamais son URL complète — celle-ci peut contenir
 * une recherche ou un identifiant de session.
 *
 * Rend `null` pour une navigation interne : ce qui nous intéresse, c'est
 * d'OÙ l'on arrive sur le site, pas comment on s'y déplace.
 */
export function provenance(referer, hoteDuSite) {
  if (!referer) return null;
  let hote;
  try {
    hote = new URL(referer).hostname.toLowerCase();
  } catch {
    return null;
  }
  if (!hote) return null;
  if (hoteDuSite && (hote === hoteDuSite || hote.endsWith(`.${hoteDuSite}`))) return null;
  return hote.slice(0, 128);
}

/** Robot ou humain — un booléen, l'en-tête lui-même n'est jamais écrit. */
export function estRobot(userAgent) {
  if (!userAgent) return true; // Un client sans agent n'est pas un navigateur.
  const ua = userAgent.toLowerCase();
  return MARQUEURS_ROBOT.some((m) => ua.includes(m));
}

/** `mobile` ou `ordinateur`. Deux valeurs : au-delà, ce serait une empreinte. */
export function appareil(userAgent) {
  if (!userAgent) return 'inconnu';
  const ua = userAgent.toLowerCase();
  return MARQUEURS_MOBILE.some((m) => ua.includes(m)) ? 'mobile' : 'ordinateur';
}

/**
 * La langue préférée, réduite à son code sur deux lettres.
 *
 * L'en-tête complet (`fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7`) est un composant
 * d'empreinte connu ; « fr » ne l'est pas.
 */
export function langue(acceptLanguage) {
  if (!acceptLanguage) return null;
  const premier = acceptLanguage.split(',')[0]?.trim().slice(0, 5) ?? '';
  const code = premier.split('-')[0].toLowerCase();
  return /^[a-z]{2}$/.test(code) ? code : null;
}

/**
 * En-têtes de pays qu'un intermédiaire peut poser.
 *
 * On lit ce qui est offert plutôt que d'embarquer une base GeoIP de plusieurs
 * mégaoctets. Si l'hébergeur n'en pose aucun, le champ vaut `null` et le
 * tableau de bord le dit — plutôt que de faire croire à une mesure absente.
 */
const ENTETES_PAYS = [
  'cf-ipcountry',        // Cloudflare
  'x-geo-country',
  'x-country-code',
  'x-appengine-country',
  'x-vercel-ip-country',
];

/**
 * Le code pays sur deux lettres.
 *
 * L'en-tête d'abord : quand l'hébergeur en pose un, il vaut mieux que notre
 * table — il voit l'adresse réelle, là où nous ne voyons que ce que le proxy
 * a bien voulu transmettre. Vérifié le 2026-08-25, Infomaniak n'en pose
 * aucun ; d'où le repli sur `geoip.mjs` et sa table embarquée.
 */
export function pays(entetes, ip = null, { resoudre = paysDeIP } = {}) {
  for (const nom of ENTETES_PAYS) {
    const brut = entetes?.[nom];
    if (typeof brut !== 'string') continue;
    const code = brut.trim().toUpperCase();
    // `XX` et `T1` sont les codes « inconnu » et « réseau Tor » de Cloudflare.
    if (/^[A-Z]{2}$/.test(code) && code !== 'XX' && code !== 'T1') return code;
  }
  return ip ? resoudre(ip) : null;
}

/**
 * Un identifiant de visiteur qui ne survit pas à la journée.
 *
 * Condensat de l'adresse IP, d'un sel secret et de la DATE. Le sel change de
 * portée chaque jour : deux visites du même appareil à 24 h d'intervalle
 * donnent deux identifiants sans rapport, et rien ne se recoud dans le temps.
 * Tronqué à 12 caractères — assez pour distinguer, trop court pour prétendre
 * remonter à quoi que ce soit.
 *
 * Rend `null` sans IP : on ne hache pas une valeur par défaut, qui
 * regrouperait tous les visiteurs anonymes sous un même identifiant.
 */
export function empreinteDuJour(ip, sel, jour) {
  if (!ip || !sel) return null;
  return createHash('sha256').update(`${sel}|${jour}|${ip}`).digest('hex').slice(0, 12);
}

/** L'heure ISO, arrondie — à la milliseconde, l'horodatage identifierait. */
export function heureRonde(date) {
  const d = new Date(date);
  d.setUTCMinutes(0, 0, 0);
  return d.toISOString();
}

/**
 * Assemble l'événement écrit sur disque.
 *
 * Tout ce qui entre ici est brut ; tout ce qui en sort est catégorisé. C'est
 * le seul endroit à relire pour savoir ce que le site conserve de ses
 * visiteurs.
 */
export function evenementDeVisite({
  chemin,
  methode = 'GET',
  statut = 200,
  entetes = {},
  ip = null,
  sel = null,
  hoteDuSite = null,
  dureeMs = null,
  maintenant = new Date(),
}) {
  const jour = maintenant.toISOString().slice(0, 10);
  return {
    ts: heureRonde(maintenant),
    chemin: cheminSeul(chemin),
    statut,
    robot: estRobot(entetes['user-agent']),
    appareil: appareil(entetes['user-agent']),
    provenance: provenance(entetes.referer, hoteDuSite),
    langue: langue(entetes['accept-language']),
    pays: pays(entetes, ip),
    visiteur: empreinteDuJour(ip, sel, jour),
    dureeMs: typeof dureeMs === 'number' ? Math.round(dureeMs) : null,
  };
}
