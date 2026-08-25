/**
 * Le pays d'une adresse IP, depuis une table embarquée.
 *
 * POURQUOI PAS UN SERVICE
 * -----------------------
 * Vérifié en production le 2026-08-25 : Infomaniak ne pose aucun en-tête de
 * géolocalisation. Il ne restait que deux voies — interroger un service tiers
 * à chaque visite, ce qui reviendrait à lui confier les adresses IP des
 * visiteurs, ou embarquer une table. Le reste du dispositif refuse d'ajouter
 * un tiers ; la table s'imposait.
 *
 * `tools/construire_table_pays.py` la produit depuis DB-IP « IP to Country
 * Lite » (CC BY 4.0). Le format y est décrit ; en deux mots : des bornes de
 * DÉBUT triées, sans les fins, parce que la base ne laisse aucun trou.
 *
 * CE QUE CE MODULE GARANTIT
 * -------------------------
 * Il est sur le chemin de chaque requête. Il ne lève jamais : table absente,
 * illisible, tronquée, adresse incompréhensible — tout rend `null`, et la
 * page continue de s'afficher. Un pays manquant est un désagrément ; une
 * exception ici arrêterait le site.
 *
 * La table n'est lue qu'au premier appel, et une seule fois. Deux mégaoctets
 * décompressés à chaque démarrage seraient payés même par un site qui ne
 * consulte jamais son tableau de bord.
 */
import { gunzipSync } from 'node:zlib';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const MAGIC = 'RECOGEO1';
const TAILLE_BORNE_V6 = 6; // uint48 : un préfixe /48 tient sur six octets.

/** Le chemin par défaut : le dépôt entier est déployé, `src/` compris. */
export function cheminTable(cwd = process.cwd()) {
  return join(cwd, 'src', 'lib', 'audience', 'pays-ip.bin.gz');
}

/**
 * L'état du chargement, mémorisé — y compris l'échec.
 *
 * Réessayer à chaque visite de lire un fichier absent coûterait un appel
 * système par requête, pour le même résultat.
 */
let table = undefined;

/** Pour les tests : oublie la table chargée. */
export function reinitialiser() {
  table = undefined;
}

/**
 * Décode l'en-tête et prépare les vues typées.
 *
 * Rend `null` sur tout ce qui n'est pas exactement le format attendu — une
 * table d'une version future ou tronquée par un transfert incomplet doit
 * désactiver la mesure, pas produire des pays au hasard.
 */
export function decoder(octets) {
  try {
    if (!octets || octets.length < 24) return null;
    const vue = new DataView(octets.buffer, octets.byteOffset, octets.byteLength);
    if (Buffer.from(octets.buffer, octets.byteOffset, 8).toString('ascii') !== MAGIC) {
      return null;
    }
    let pos = 8;
    const version = vue.getUint16(pos); pos += 2;
    if (version !== 1) return null;
    const edition = Buffer.from(octets.buffer, octets.byteOffset + pos, 8)
      .toString('ascii').trim();
    pos += 8;

    const nbPays = vue.getUint16(pos); pos += 2;
    const pays = [];
    for (let i = 0; i < nbPays; i += 1) {
      pays.push(Buffer.from(octets.buffer, octets.byteOffset + pos, 2).toString('ascii'));
      pos += 2;
    }

    const n4 = vue.getUint32(pos); pos += 4;
    const debut4 = pos; pos += n4 * 4;
    const index4 = pos; pos += n4;

    const n6 = vue.getUint32(pos); pos += 4;
    const debut6 = pos; pos += n6 * TAILLE_BORNE_V6;
    const index6 = pos; pos += n6;

    // La longueur annoncée doit correspondre à la longueur réelle : sinon la
    // recherche binaire lirait au-delà du tampon.
    if (pos !== octets.byteLength) return null;

    return { vue, octets, pays, edition, n4, debut4, index4, n6, debut6, index6 };
  } catch {
    return null;
  }
}

/** Charge la table une fois, en mémorisant même l'échec. */
function chargee(chemin) {
  if (table !== undefined) return table;
  try {
    table = decoder(gunzipSync(readFileSync(chemin ?? cheminTable())));
  } catch {
    // Fichier absent : c'est le cas d'un fork qui n'a pas construit la table.
    table = null;
  }
  return table;
}

/** L'édition de la table chargée, pour l'afficher — ou `null`. */
export function editionTable(chemin) {
  return chargee(chemin)?.edition ?? null;
}

/** `1.2.3.4` → entier non signé, ou `null` si ce n'en est pas une. */
export function versEntierV4(texte) {
  const parts = texte.split('.');
  if (parts.length !== 4) return null;
  let n = 0;
  for (const part of parts) {
    // `+part` accepterait ' 1', '1e2' ou '' : une adresse n'est que des
    // chiffres, et au plus trois.
    if (!/^\d{1,3}$/.test(part)) return null;
    const octet = Number(part);
    if (octet > 255) return null;
    n = n * 256 + octet;
  }
  return n;
}

/**
 * `2a01:e0a:...` → les 48 premiers bits, ou `null`.
 *
 * Quarante-huit bits tiennent dans un `Number` sans perte (moins de 2^53) :
 * pas besoin de `BigInt`, dont le coût se paierait à chaque visite.
 */
export function versPrefixeV6(texte) {
  const doubles = texte.split('::');
  if (doubles.length > 2) return null;

  const decouper = (bloc) => (bloc === '' ? [] : bloc.split(':'));
  const gauche = decouper(doubles[0]);
  const droite = doubles.length === 2 ? decouper(doubles[1]) : null;

  // Forme mixte `::ffff:192.0.2.1` : c'est une IPv4, traitée comme telle en
  // amont. Ici on refuse, plutôt que d'en tirer un préfixe qui n'a pas de sens.
  if ([...gauche, ...(droite ?? [])].some((g) => g.includes('.'))) return null;

  let groupes;
  if (droite === null) {
    if (gauche.length !== 8) return null;
    groupes = gauche;
  } else {
    const manquants = 8 - gauche.length - droite.length;
    if (manquants < 1) return null;
    groupes = [...gauche, ...Array(manquants).fill('0'), ...droite];
  }

  let n = 0;
  for (let i = 0; i < 3; i += 1) {
    if (!/^[0-9a-fA-F]{1,4}$/.test(groupes[i])) return null;
    n = n * 65536 + parseInt(groupes[i], 16);
  }
  return n;
}

/**
 * Le plus grand index dont la borne est ≤ `valeur`, ou -1.
 *
 * `lire(i)` isole la façon de lire une borne : les bornes IPv4 tiennent sur
 * quatre octets, les IPv6 sur six.
 */
function rechercher(n, lire, valeur) {
  let bas = 0;
  let haut = n - 1;
  let trouve = -1;
  while (bas <= haut) {
    const milieu = (bas + haut) >> 1;
    if (lire(milieu) <= valeur) {
      trouve = milieu;
      bas = milieu + 1;
    } else {
      haut = milieu - 1;
    }
  }
  return trouve;
}

/**
 * Le code pays d'une adresse, ou `null`.
 *
 * `ZZ` est le code « inconnu » de la base : il vaut `null` ici, pour que le
 * tableau de bord ne présente pas une absence comme un pays.
 */
export function paysDeIP(ip, { chemin } = {}) {
  if (typeof ip !== 'string' || !ip) return null;
  const t = chargee(chemin);
  if (!t) return null;

  try {
    let adresse = ip.trim();
    // `::ffff:192.0.2.1` — une IPv4 vue à travers une pile IPv6. Node en
    // produit dès qu'un socket est en double pile.
    const mappee = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(adresse);
    if (mappee) adresse = mappee[1];

    let rang;
    if (adresse.includes(':')) {
      const prefixe = versPrefixeV6(adresse);
      if (prefixe === null) return null;
      const lire = (i) => {
        const p = t.debut6 + i * TAILLE_BORNE_V6;
        // uint48 gros-boutiste : deux octets de poids fort, puis quatre.
        return t.vue.getUint16(p) * 4294967296 + t.vue.getUint32(p + 2);
      };
      const i = rechercher(t.n6, lire, prefixe);
      if (i < 0) return null;
      rang = t.octets[t.index6 + i];
    } else {
      const entier = versEntierV4(adresse);
      if (entier === null) return null;
      const lire = (i) => t.vue.getUint32(t.debut4 + i * 4);
      const i = rechercher(t.n4, lire, entier);
      if (i < 0) return null;
      rang = t.octets[t.index4 + i];
    }

    const code = t.pays[rang];
    return code && code !== 'ZZ' ? code : null;
  } catch {
    return null;
  }
}
