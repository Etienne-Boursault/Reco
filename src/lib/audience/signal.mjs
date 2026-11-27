/**
 * Le signal « page vue » : `POST /api/vue`, reçu côté Node.
 *
 * POURQUOI (AU-1 A, 2026-11-27)
 * -----------------------------
 * Une visite mesurée côté serveur ne dit pas si un navigateur a réellement
 * affiché la page : un robot qui sait demander du HTML passe pour un
 * visiteur. Le navigateur envoie donc un petit signal une fois la page
 * affichée (tranche suivante) ; ce module le reçoit et l'écrit comme une ligne
 * `nature: 'signal'` dans le MÊME fichier JSONL du jour que les visites. La
 * purge de `retention.mjs` s'applique donc sans rien changer. Un visiteur-jour
 * qui a envoyé un signal pourra être dit « confirmé ».
 *
 * REÇU PAR NODE, PAS PAR ASTRO
 * ----------------------------
 * Il faut la même empreinte du jour que les visites (`adresseCliente`,
 * `empreinteDuJour`), donc le même chemin de code. Un signal n'est pas une
 * page vue : `/api/` n'est jamais mesuré comme visite (`estUnePage`).
 *
 * CE QUI EST ASSUMÉ
 * -----------------
 * - Un signal sous `Sec-GPC: 1` ou `DNT: 1` est ACCEPTÉ : il ne porte aucun
 *   identifiant, seulement le chemin et l'empreinte du jour que le serveur
 *   calcule déjà pour toute visite. C'est le navigateur (tranche C) qui
 *   cessera d'en envoyer sous refus.
 * - Sans sel (`RECO_AUDIENCE_SALT`), la ligne s'écrit avec `visiteur: null`,
 *   comme une visite : un sel absent ne fait pas taire la mesure.
 * - Origine : on compare le NOM D'HÔTE de `Origin` à celui de `Host`, sans le
 *   protocole et sans `SITE_URL`. Derrière le mandataire la requête arrive en
 *   http et `SITE_URL` est absente : l'origine attendue de `/api/click`, tirée
 *   de cette variable, y répondait 403 à tout le monde. `Sec-Fetch-Site` doit
 *   valoir `same-origin` quand il est présent.
 * - shortcut : le plafond de lignes du jour et la table de limitation sont en
 *   mémoire, ils repartent de zéro au redémarrage ; à revoir si le serveur
 *   tourne en plusieurs processus.
 * - Le passage à minuit UTC change d'un coup le fichier du jour et l'empreinte
 *   (R-13) : les deux se calculent à partir de la même horloge.
 *
 * Réponses : 204 (écrit, ou écriture impossible : journalisée, jamais
 * remontée), 400 (corps ou chemin invalide), 403 (origine), 405, 408
 * (corps trop lent), 413 (corps > 1 Kio), 429 (30 signaux par minute).
 */
import { cheminSeul, estUnePage, evenementDeSignal } from './derive.mjs';
import { adresseCliente, sourceDuChemin } from './mesure.mjs';
import { enregistrer } from './storage.mjs';

const MINUTE_MS = 60_000;

/** Les pages d'administration du réseau de sites ne sont pas des visites. */
const estMeta = (chemin) => /^\/meta(\/|\?|$)/.test(chemin);

/** Le nom d'hôte de `Origin` est-il celui de `Host` ? Voir « origine » plus haut. */
function memeHote(entetes) {
  const site = entetes['sec-fetch-site'];
  if (site !== undefined && site !== 'same-origin') return false;
  const { origin, host } = entetes;
  if (typeof origin !== 'string' || typeof host !== 'string') return false;
  try {
    return new URL(origin).hostname === new URL(`http://${host}`).hostname;
  } catch {
    return false;
  }
}

function repondre(res, statut, entetes = {}) {
  res.writeHead(statut, entetes);
  res.end();
}

/**
 * Lit le corps en flux, coupé à `max` octets. Rend `{ corps }` ou `{ erreur }`
 * (`trop-gros`, `coupe`, `delai`). Au-delà de `max`, on cesse d'écouter : le
 * reste n'est jamais lu en entier.
 */
function lireCorps(req, max, delaiMs) {
  return new Promise((fin) => {
    const morceaux = [];
    let taille = 0;
    let fini = false;
    const terminer = (resultat) => {
      if (fini) return;
      fini = true;
      clearTimeout(minuteur);
      req.off('data', surDonnee);
      fin(resultat);
    };
    const surDonnee = (morceau) => {
      taille += morceau.length;
      if (taille > max) return terminer({ erreur: 'trop-gros' });
      morceaux.push(morceau);
    };
    const minuteur = setTimeout(() => terminer({ erreur: 'delai' }), delaiMs);
    req.on('data', surDonnee);
    req.once('end', () => terminer({ corps: Buffer.concat(morceaux).toString('utf8') }));
    // Gardé après la fin : sans écouteur, un `error` tardif ferait tomber le serveur.
    req.on('error', () => terminer({ erreur: 'coupe' }));
    req.once('aborted', () => terminer({ erreur: 'coupe' }));
  });
}

/** Le chemin du signal, ou `null` s'il ne désigne pas une page mesurable. */
function cheminDuCorps(corps) {
  let valeur;
  try {
    valeur = JSON.parse(corps);
  } catch {
    return null;
  }
  const chemin = valeur?.chemin;
  if (typeof chemin !== 'string' || chemin.length > 512) return null;
  return estUnePage(chemin, 'GET') && !estMeta(chemin) ? chemin : null;
}

/**
 * Crée le gestionnaire de `POST /api/vue`. Chaque appel a SON état (table de
 * limitation, compteur du jour) : les tests en prennent un neuf.
 */
export function creerSignal(options = {}) {
  const {
    cwd = process.cwd(),
    sourcesConnues = null,
    ecrire = enregistrer,
    horloge = Date.now,
    journal = console,
    delaiMs = 5000,
    maxCorps = 1024,
    parMinute = 30,
    maxEmpreintes = 10_000,
    maxLignesJour = 20_000,
  } = options;

  const table = new Map(); // empreinte -> { debut, n } ; les plus anciennes tombent
  let jour = null;
  let lignes = 0;
  let plafondDit = false;
  let ecritureDite = false;

  const limite = (cle, maintenant) => {
    const e = table.get(cle);
    if (e && maintenant - e.debut < MINUTE_MS) return ++e.n > parMinute;
    table.delete(cle);
    if (table.size >= maxEmpreintes) table.delete(table.keys().next().value);
    table.set(cle, { debut: maintenant, n: 1 });
    return false;
  };

  return async function signaler(req, res) {
    try {
      if (req.method !== 'POST') return repondre(res, 405, { Allow: 'POST' });
      const entetes = req.headers ?? {};
      if (!memeHote(entetes)) return repondre(res, 403);

      const maintenant = new Date(horloge());
      const ip = adresseCliente(req);
      const sel = options.sel ?? process.env.RECO_AUDIENCE_SALT ?? null;

      if (Number(entetes['content-length']) > maxCorps) {
        return repondre(res, 413, { Connection: 'close' });
      }
      const { corps, erreur } = await lireCorps(req, maxCorps, delaiMs);
      if (erreur === 'trop-gros') return repondre(res, 413, { Connection: 'close' });
      if (erreur === 'delai') return repondre(res, 408, { Connection: 'close' });
      if (erreur) return undefined; // client parti : personne à qui répondre

      const chemin = cheminDuCorps(corps);
      if (chemin === null) return repondre(res, 400);

      const ligne = evenementDeSignal({ chemin, ip, sel, maintenant });
      if (limite(ligne.visiteur ?? ip ?? 'inconnu', maintenant.getTime())) {
        return repondre(res, 429);
      }

      const aujourdhui = ligne.ts.slice(0, 10);
      if (aujourdhui !== jour) {
        jour = aujourdhui;
        lignes = 0;
        plafondDit = false;
      }
      if (lignes >= maxLignesJour) {
        if (!plafondDit) {
          plafondDit = true;
          journal.warn?.(`[audience] plafond de ${maxLignesJour} signaux atteint pour ${jour}`);
        }
        return repondre(res, 204);
      }

      let ecrit = false;
      try {
        ecrit = ecrire(ligne, sourceDuChemin(ligne.chemin, sourcesConnues), cwd, journal);
      } catch (err) {
        // `enregistrer` n'en lève pas ; une doublure ou une future version, si.
        journal.warn?.('[audience] signal : écriture impossible :', err?.message ?? err);
      }
      if (ecrit) lignes += 1;
      else if (!ecritureDite) {
        ecritureDite = true;
        journal.warn?.(`[audience] signal non écrit (${jour}) ; réponse 204 quand même`);
      }
      return repondre(res, 204);
    } catch (err) {
      journal.error?.('[audience] signal : erreur inattendue :', err?.message ?? err);
      if (!res.headersSent) repondre(res, 500);
      return undefined;
    }
  };
}
