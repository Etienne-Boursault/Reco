/**
 * sonde_verifier.mjs — mener, depuis le poste, les vérifications MES-1.
 *
 * POURQUOI CE SCRIPT
 * ------------------
 * La sonde (`src/server/sonde.mjs`) répond chez l'hébergeur ; ce script lui
 * pose les questions et compare ses réponses à ce qu'il a envoyé. Il est
 * temporaire, comme elle : la PR qui retire la sonde le retire aussi.
 *
 * LA CLÉ NE S'AFFICHE JAMAIS
 * --------------------------
 * Elle est lue dans `RECO_SONDE_CLE`, chargée depuis un fichier que tu remplis
 * toi-même, jamais passée en argument (la ligne de commande reste dans
 * l'historique) :
 *
 *     node --env-file=$HOME/.reco-sonde.env scripts/sonde_verifier.mjs tout
 *
 * avec, dans `~/.reco-sonde.env` : `RECO_SONDE_CLE=…` et, au besoin,
 * `RECO_SONDE_URL=…` (par défaut, le site public).
 *
 * LES COMMANDES
 * -------------
 *   processus    50 requêtes de suite : combien de processus répondent ?
 *   v1           des envois de 1, 4 et 8 Mio : arrivent-ils en entier ?
 *   v2           la base : version, transaction, verrou, CHECK, mode strict
 *   v3-poser     pose le témoin du dossier de données (une seule fois)
 *   v3-relire    relit le témoin, après un build puis après un redémarrage
 *   redemarrage  interroge la sonde chaque demi-seconde pendant que tu
 *                redémarres le site, et mesure la coupure
 *   tout         processus, v1, v2 et v3-poser, dans cet ordre
 */
import { createHash, randomBytes } from 'node:crypto';

const CLE = process.env.RECO_SONDE_CLE;
const BASE = (process.env.RECO_SONDE_URL || 'https://unebonnere.co').replace(/\/$/, '');
const MIO = 1024 * 1024;

/** Un appel à la sonde. Rend le statut et le corps, jamais d'exception. */
async function appeler(chemin, { methode = 'GET', corps } = {}) {
  try {
    const reponse = await fetch(`${BASE}/__sonde/${chemin}`, {
      method: methode,
      headers: { Authorization: `Bearer ${CLE}` },
      body: corps,
      signal: AbortSignal.timeout(120_000),
    });
    const texte = await reponse.text();
    let json = null;
    try { json = JSON.parse(texte); } catch { /* une page d'erreur, pas la sonde */ }
    return { statut: reponse.status, json };
  } catch (err) {
    return { statut: 0, erreur: err.cause?.code ?? err.name };
  }
}

async function processus() {
  const pids = new Map();
  for (let i = 0; i < 50; i += 1) {
    const { statut, json } = await appeler('processus');
    const cle = statut === 200 ? json.pid : `statut ${statut}`;
    pids.set(cle, (pids.get(cle) ?? 0) + 1);
  }
  return { requetes: 50, reponses: Object.fromEntries(pids) };
}

async function v1() {
  const lignes = [];
  for (const taille of [1, 4, 8]) {
    const corps = randomBytes(taille * MIO);
    const sha256 = createHash('sha256').update(corps).digest('hex');
    const debut = performance.now();
    const { statut, json, erreur } = await appeler('v1', { methode: 'POST', corps });
    lignes.push({
      envoye: `${taille} Mio`,
      statut,
      erreur,
      octetsLus: json?.octets,
      entier: json?.octets === corps.length && json?.sha256 === sha256,
      dureeMs: Math.round(performance.now() - debut),
    });
  }
  return lignes;
}

async function redemarrage() {
  const premier = await appeler('processus');
  if (premier.statut !== 200) return { erreur: 'la sonde ne répond pas avant le redémarrage', ...premier };
  const ancien = premier.json.pid;
  console.error(`Processus ${ancien} en service. Redémarre le site dans le Manager ; j'attends…`);
  let derniereReponse = Date.now();
  let echecs = 0;
  const limite = Date.now() + 10 * 60_000;
  while (Date.now() < limite) {
    await new Promise((r) => setTimeout(r, 500));
    const { statut, json } = await appeler('processus');
    if (statut === 200 && json.pid === ancien) { derniereReponse = Date.now(); continue; }
    if (statut === 200) {
      return { ancien, nouveau: json.pid, coupureMs: Date.now() - derniereReponse, requetesEnEchec: echecs };
    }
    echecs += 1;
  }
  return { erreur: 'aucun nouveau processus en 10 minutes', ancien, requetesEnEchec: echecs };
}

const COMMANDES = {
  processus,
  v1,
  v2: async () => (await appeler('v2', { methode: 'POST' })),
  'v3-poser': async () => (await appeler('v3', { methode: 'POST' })),
  'v3-relire': async () => (await appeler('v3')),
  redemarrage,
  tout: async () => ({
    processus: await processus(),
    v1: await v1(),
    v2: await appeler('v2', { methode: 'POST' }),
    v3: await appeler('v3', { methode: 'POST' }),
  }),
};

const commande = COMMANDES[process.argv[2]];
if (!CLE || !commande) {
  console.error(`Usage : node --env-file=… scripts/sonde_verifier.mjs <${Object.keys(COMMANDES).join('|')}>`);
  console.error(CLE ? 'Commande inconnue.' : 'RECO_SONDE_CLE manque dans l’environnement.');
  process.exit(2);
}
console.log(JSON.stringify({ site: BASE, le: new Date().toISOString(), resultat: await commande() }, null, 2));
