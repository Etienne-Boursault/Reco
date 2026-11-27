/**
 * Ne pas mesurer les visites de l'éditeur : une liste d'adresses à ignorer.
 *
 * DEMANDE (Étienne, 27/11/2026, 17 h 24) ET DÉCISION (R-14)
 * ---------------------------------------------------------
 * « il faut ne pas compter les visites qui viennent de ma propre IP ». Son
 * adresse publique change (deux fois en août) : un nom de DNS dynamique la
 * suit. `RECO_AUDIENCE_EXCLURE` liste des noms d'hôte et des adresses IP,
 * séparés par des virgules. Les noms sont résolus (A et AAAA) au démarrage,
 * puis toutes les 5 minutes ; les adresses écrites telles quelles sont prises
 * sans résolution. Une requête dont l'adresse cliente est dans l'ensemble
 * n'écrit rien : ni visite, ni signal, ni clic.
 *
 * LA VÉRIFICATION NE BLOQUE JAMAIS
 * --------------------------------
 * `exclut` lit un ensemble en mémoire, remplacé d'un bloc après chaque
 * résolution : aucune requête n'attend le DNS. Une résolution qui échoue garde
 * la dernière réponse connue du nom, par famille (A, AAAA) ; seule la réponse
 * « aucun enregistrement » (ENODATA) vide la famille. Le minuteur est `unref` :
 * il ne retient pas le processus à l'arrêt.
 *
 * LIMITES ASSUMÉES
 * ----------------
 * - Une visite depuis le réseau mobile (ou tout autre réseau que celui du nom)
 *   compte : la liste ne connaît que ce qu'on lui donne.
 * - Les mesures déjà écrites ne sont pas corrigées.
 * - Une adresse qui change compte encore pendant au plus 5 minutes, plus le
 *   délai de mise à jour du DNS dynamique.
 *
 * Le nom du DNS dynamique est de l'infrastructure privée : il ne vit que dans
 * la variable de l'hébergeur, jamais dans le dépôt, ni dans les journaux.
 */
import dns from 'node:dns/promises';
import { isIP } from 'node:net';

const CINQ_MINUTES_MS = 5 * 60 * 1000;
const FAMILLES = ['4', '6'];

/**
 * La forme canonique d'une adresse, ou `null` si ce n'est pas une adresse.
 *
 * IPv6 en minuscules compressées (via `URL`) ; une IPv4 vue à travers une pile
 * IPv6 (`::ffff:192.0.2.7`, ou `::ffff:c000:207`) redevient l'IPv4.
 */
export function normaliser(adresse) {
  if (typeof adresse !== 'string') return null;
  const a = adresse.trim();
  const version = isIP(a);
  if (version === 4) return a;
  if (version !== 6) return null;
  let v6;
  try {
    v6 = new URL(`http://[${a}]`).hostname.slice(1, -1);
  } catch {
    return null; // identifiant de zone (`fe80::1%eth0`) : pas une adresse publique
  }
  const mappee = /^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(v6);
  if (!mappee) return v6;
  const [haut, bas] = [parseInt(mappee[1], 16), parseInt(mappee[2], 16)];
  return `${haut >> 8}.${haut & 255}.${bas >> 8}.${bas & 255}`;
}

/**
 * Crée l'exclusion. Résolveur et minuteur sont injectables (tests sans DNS).
 * Rend `{ exclut(ip), rafraichir(), pret, arreter() }`.
 */
export function creerExclusion(options = {}) {
  const {
    liste = process.env.RECO_AUDIENCE_EXCLURE,
    resolveur = dns,
    planifier = setInterval,
    annuler = clearInterval,
    periodeMs = CINQ_MINUTES_MS,
    journal = console,
  } = options;

  const fixes = new Set();
  const noms = [];
  for (const jeton of (liste ?? '').split(',').map((s) => s.trim()).filter(Boolean)) {
    const adresse = normaliser(jeton);
    if (adresse) fixes.add(adresse);
    else noms.push(jeton.toLowerCase());
  }

  const connues = new Map(); // `${nom}|${famille}` -> Set d'adresses : la dernière réponse
  const enPanne = new Set(); // clés dont l'échec a déjà été dit
  let courant = new Set(fixes);

  const rafraichir = async () => {
    await Promise.all(noms.flatMap((nom) => FAMILLES.map(async (famille) => {
      const cle = `${nom}|${famille}`;
      try {
        const reponse = await resolveur[`resolve${famille}`](nom);
        connues.set(cle, new Set(reponse.map(normaliser).filter(Boolean)));
        enPanne.delete(cle);
      } catch (err) {
        if (err?.code === 'ENODATA') {
          connues.set(cle, new Set());
          enPanne.delete(cle);
        } else if (!enPanne.has(cle)) {
          enPanne.add(cle);
          // Pas de nom dans le journal : c'est de l'infrastructure privée.
          journal.warn?.(`[audience] exclusion : résolution A${famille === '6' ? 'AAA' : ''} en échec (${err?.code ?? 'inconnu'}), dernière réponse gardée`);
        }
      }
    })));
    courant = new Set([...fixes, ...[...connues.values()].flatMap((s) => [...s])]);
  };

  const pret = noms.length ? rafraichir() : Promise.resolve();
  const minuteur = noms.length ? planifier(rafraichir, periodeMs) : null;
  minuteur?.unref?.();

  return {
    exclut: (ip) => {
      const adresse = normaliser(ip);
      return adresse !== null && courant.has(adresse);
    },
    rafraichir,
    pret,
    arreter: () => { if (minuteur) annuler(minuteur); },
  };
}
