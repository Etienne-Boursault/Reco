/**
 * La sonde des trois vérifications chez l'hébergeur (PR-VERIF, MES-1).
 *
 * POURQUOI ELLE EXISTE
 * --------------------
 * La V2 range le catalogue dans une base MariaDB chez l'hébergeur, et le
 * reçoit par des envois POST depuis venus. Trois faits n'ont jamais été
 * vérifiés sur place, et la suite du plan en dépend :
 *
 *   V1. un envoi d'un mégaoctet arrive-t-il en entier ? Seuls 80 Ko lus
 *       avaient été vérifiés ;
 *   V2. le site joint-il sa base, avec des transactions, des verrous de ligne,
 *       des contraintes `CHECK` et le mode strict ?
 *   V3. un fichier écrit à l'exécution survit-il au build suivant ?
 *
 * La sonde répond à ces trois questions, plus deux relevés de la même séance :
 * l'identifiant du processus (combien de processus répondent ?) et son heure
 * de démarrage (combien dure un redémarrage ?).
 *
 * POURQUOI ELLE NE RISQUE RIEN
 * ----------------------------
 * Sans `RECO_SONDE_CLE`, ou sans la bonne clé dans l'en-tête `Authorization`,
 * elle rend la main et la requête suit son chemin ordinaire : un 404, comme
 * pour n'importe quelle adresse inconnue. Rien ne distingue la sonde éteinte
 * d'une sonde qu'on ne sait pas ouvrir. Elle ne touche ni au catalogue ni aux
 * pages : sa seule table, `sonde_essai`, est supprimée à la fin de chaque
 * passage, et son seul fichier est un témoin de quelques octets.
 *
 * Elle est temporaire : une seconde PR la retire, une fois les résultats
 * notés dans la documentation de la V2.
 */
import { createHash, timingSafeEqual } from 'node:crypto';
import { mkdirSync, readFileSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

/** Le préfixe de toutes les adresses de la sonde. */
export const PREFIXE = '/__sonde/';

/** Le nom du fichier témoin de V3, dans le dossier de données. */
export const TEMOIN = 'sonde-temoin.json';

/** Le nombre de requêtes `SELECT 1` dont la sonde prend la médiane (V2). */
const MESURES = 20;

/**
 * Compare la clé reçue à la clé attendue, en temps constant.
 *
 * Les deux côtés passent par SHA-256 : `timingSafeEqual` exige deux tampons
 * de même longueur, et comparer les longueurs d'abord révélerait celle de la
 * clé.
 */
export function autorise(req, cle) {
  if (!cle) return false;
  const recu = createHash('sha256').update(String(req.headers.authorization ?? '')).digest();
  const attendu = createHash('sha256').update(`Bearer ${cle}`).digest();
  return timingSafeEqual(recu, attendu);
}

/** Répond en JSON, jamais mis en cache : chaque réponse est une mesure. */
function repondre(res, statut, corps) {
  const texte = JSON.stringify(corps);
  res.writeHead(statut, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(texte),
    'Cache-Control': 'no-store',
  });
  res.end(texte);
}

/** Le processus qui répond, et l'heure où il a démarré. */
export function processus() {
  const maintenant = Date.now();
  return {
    pid: process.pid,
    demarreLe: new Date(maintenant - process.uptime() * 1000).toISOString(),
    maintenant: new Date(maintenant).toISOString(),
  };
}

/**
 * V1 : lit le corps en entier, sans le garder, et dit ce qui est arrivé.
 *
 * Le client compare le nombre d'octets et le SHA-256 à ce qu'il a envoyé. Un
 * corps tronqué par un intermédiaire se voit ainsi, même si la requête
 * réussit.
 */
export async function lireEnvoi(req) {
  const empreinte = createHash('sha256');
  let octets = 0;
  for await (const morceau of req) {
    octets += morceau.length;
    empreinte.update(morceau);
  }
  return {
    octets,
    sha256: empreinte.digest('hex'),
    annonce: req.headers['content-length'] ?? null,
  };
}

/** Les variables de connexion à la base, toutes lues au moment de l'appel. */
export const VARIABLES_BDD = [
  'RECO_BDD_HOTE', 'RECO_BDD_NOM', 'RECO_BDD_UTILISATEUR', 'RECO_BDD_MOT_DE_PASSE',
];

/**
 * Ouvre une connexion avec les variables du Manager.
 *
 * `multipleStatements` reste éteint : une requête n'exécute jamais qu'une
 * instruction (`03` § 2.6). L'import est dynamique pour que le serveur démarre
 * même si `mysql2` manquait : seule la vérification V2 échouerait.
 */
export async function connecterMariaDB(env = process.env) {
  const { createConnection } = await import('mysql2/promise');
  return createConnection({
    host: env.RECO_BDD_HOTE,
    port: Number(env.RECO_BDD_PORT) || 3306,
    database: env.RECO_BDD_NOM,
    user: env.RECO_BDD_UTILISATEUR,
    password: env.RECO_BDD_MOT_DE_PASSE,
    charset: 'UTF8MB4_BIN',
    multipleStatements: false,
    connectTimeout: 10_000,
  });
}

/** Le code d'erreur d'une requête qui doit échouer, ou `null` si elle a réussi. */
async function refus(requete) {
  try {
    await requete;
    return null;
  } catch (err) {
    return err.code ?? String(err.message);
  }
}

/** Les réglages que le site fixera à chaque connexion (`02` § 9). */
async function preparer(connexion) {
  await connexion.query("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION'");
  await connexion.query('SET NAMES utf8mb4 COLLATE utf8mb4_bin');
}

const CREER_TABLE = `CREATE TABLE sonde_essai (
  cle VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
  valeur VARCHAR(8) NOT NULL,
  CONSTRAINT sonde_format_cle CHECK (cle REGEXP '^[a-z0-9]+$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`;

const INSERER = 'INSERT INTO sonde_essai (cle, valeur) VALUES (?, ?)';
const VERROUILLER = 'SELECT valeur FROM sonde_essai WHERE cle = ? FOR UPDATE';

/**
 * V2 : la base répond-elle comme la V2 l'exige ?
 *
 * Chaque étape note son résultat ; une erreur imprévue arrête la suite et dit
 * à quelle étape elle est survenue. Les refus attendus sont rendus par leur
 * code : `ER_LOCK_WAIT_TIMEOUT` pour le verrou, `ER_CONSTRAINT_FAILED` pour
 * la contrainte `CHECK`, `ER_DATA_TOO_LONG` pour le mode strict. La table est
 * supprimée dans tous les cas.
 */
export async function verifierBase({ env = process.env, connecter = connecterMariaDB } = {}) {
  const manquantes = VARIABLES_BDD.filter((nom) => !env[nom]);
  if (manquantes.length) return { ok: false, etape: 'variables', manquantes };

  const resultat = { ok: false, etape: 'connexion' };
  const connexions = [];
  try {
    const a = await connecter(env);
    connexions.push(a);
    const b = await connecter(env);
    connexions.push(b);
    await preparer(a);
    await preparer(b);

    resultat.etape = 'version';
    const [[{ version }]] = await a.query('SELECT VERSION() AS version');
    resultat.version = version;

    resultat.etape = 'table';
    await a.query('DROP TABLE IF EXISTS sonde_essai');
    await a.query(CREER_TABLE);

    resultat.etape = 'transaction';
    await a.beginTransaction();
    await a.query(INSERER, ['essai', 'été']);
    const [lu] = await a.query('SELECT valeur FROM sonde_essai WHERE cle = ?', ['essai']);
    await a.commit();
    resultat.transaction = lu[0]?.valeur === 'été';

    // Deux connexions, une seule ligne : la seconde doit attendre la première.
    resultat.etape = 'verrou';
    await b.query('SET SESSION innodb_lock_wait_timeout = 1');
    await a.beginTransaction();
    await a.query(VERROUILLER, ['essai']);
    await b.beginTransaction();
    resultat.verrou = await refus(b.query(VERROUILLER, ['essai']));
    await a.commit();
    resultat.verrouLibere = (await refus(b.query(VERROUILLER, ['essai']))) === null;
    await b.commit();

    resultat.etape = 'contraintes';
    resultat.check = await refus(a.query(INSERER, ['Pas bon', 'x']));
    resultat.strict = await refus(a.query(INSERER, ['long', 'neuf lettres']));

    resultat.etape = 'duree';
    const durees = [];
    for (let i = 0; i < MESURES; i += 1) {
      const debut = performance.now();
      await a.query('SELECT 1');
      durees.push(performance.now() - debut);
    }
    durees.sort((x, y) => x - y);
    resultat.dureeMs = Math.round(durees[MESURES / 2] * 100) / 100;

    resultat.etape = 'fin';
    resultat.ok = true;
  } catch (err) {
    resultat.erreur = err.code ?? String(err.message);
  } finally {
    // Une connexion déjà tombée ne doit pas empêcher de fermer l'autre.
    if (connexions[0]) await refus(connexions[0].query('DROP TABLE IF EXISTS sonde_essai'));
    for (const connexion of connexions) await refus(connexion.end());
  }
  return resultat;
}

/** Le dossier de données du site, que le build ne doit pas effacer (V3). */
export function dossierDonnees(env = process.env) {
  return resolve(env.RECO_DONNEES_DIR || 'reco-donnees');
}

/** Lit le témoin, ou `null` s'il n'existe pas. */
function lireTemoin(chemin) {
  try {
    return JSON.parse(readFileSync(chemin, 'utf8'));
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw err;
  }
}

/**
 * V3, premier temps : pose le témoin s'il n'existe pas encore.
 *
 * Jamais réécrit : c'est sa date de création qui prouve, après un build puis
 * un redémarrage, que le fichier a survécu.
 */
export function poserTemoin(dossier, { ecrire = writeFileSync } = {}) {
  mkdirSync(dossier, { recursive: true });
  const chemin = join(dossier, TEMOIN);
  let cree = true;
  try {
    ecrire(chemin, JSON.stringify({ ecritLe: new Date().toISOString(), pid: process.pid }),
      { flag: 'wx' });
  } catch (err) {
    if (err.code !== 'EEXIST') throw err;
    cree = false;
  }
  return { cree, temoin: lireTemoin(chemin) };
}

/** V3, second temps : le témoin est-il là, et peut-on encore écrire ? */
export function relireTemoin(dossier, { ecrire = writeFileSync } = {}) {
  const essai = join(dossier, '.sonde-ecriture');
  let ecriture = true;
  try {
    mkdirSync(dossier, { recursive: true });
    ecrire(essai, 'essai');
    unlinkSync(essai);
  } catch {
    ecriture = false;
  }
  return { temoin: lireTemoin(join(dossier, TEMOIN)), ecriture };
}

/** Les routes de la sonde, par méthode et chemin. */
const ROUTES = {
  'GET processus': async () => processus(),
  'POST v1': async (req) => lireEnvoi(req),
  'POST v2': async (req, options) => verifierBase(options),
  'POST v3': async (req, options) => poserTemoin(dossierDonnees(options.env)),
  'GET v3': async (req, options) => relireTemoin(dossierDonnees(options.env)),
};

/**
 * Traite la requête si elle s'adresse à la sonde avec la bonne clé.
 *
 * Rend `true` quand la sonde répond, `false` pour laisser la requête suivre
 * son chemin ordinaire, qui finit en 404. Le travail est asynchrone, mais la
 * décision est immédiate : `traiter` sait aussitôt s'il doit continuer.
 */
export function sonder(req, res, options = {}) {
  const env = options.env ?? process.env;
  const url = req.url || '/';
  if (!url.startsWith(PREFIXE)) return false;
  if (!autorise(req, env.RECO_SONDE_CLE)) return false;
  const nom = new URL(url, 'http://sonde').pathname.slice(PREFIXE.length);
  const route = ROUTES[`${req.method} ${nom}`];
  if (!route) return false;
  route(req, { ...options, env }).then(
    (corps) => repondre(res, 200, corps),
    (err) => repondre(res, 500, { erreur: err.code ?? String(err.message) }),
  );
  return true;
}
