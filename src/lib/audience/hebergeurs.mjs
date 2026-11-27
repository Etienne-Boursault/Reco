/**
 * Cette adresse IP appartient-elle à un hébergeur ? Lu dans une table embarquée.
 *
 * DÉCISION (AU-1 A, 2026-11-27)
 * -----------------------------
 * Le tableau `/audience` mélangeait robots et visiteurs. Un navigateur
 * d'humain vient rarement d'un centre de données ou d'un VPN : on repère donc,
 * au moment de la mesure, les adresses d'hébergeurs, et `derive.mjs` écrit un
 * simple booléen `hebergeur`. L'adresse elle-même n'est jamais conservée, et
 * aucun appel ne sort du processus : la table est embarquée, comme celle des
 * pays (`geoip.mjs`).
 *
 * `tools/construire_table_hebergeurs.py` la produit (X4BNet `lists_vpn`, MIT,
 * croisé avec DB-IP « IP to ASN Lite », CC BY 4.0) et décrit le format
 * RECOHEB1 : des paires début/fin triées, IPv4 et IPv6 tronqué au /48. Les
 * réseaux de vrais visiteurs (WARP, iCloud Private Relay…) en sont écartés
 * (R-8) : un visiteur réel classé « hébergeur » sortirait du compte sans que
 * personne le voie.
 *
 * CE QUE CE MODULE GARANTIT
 * -------------------------
 * Il est sur le chemin de chaque requête. Il ne lève jamais : table absente,
 * illisible, tronquée, adresse incompréhensible, tout rend `false` (la table est
 * validée au chargement, aucune lecture ne sort du tampon). La table
 * n'est lue qu'au premier appel, une seule fois, échec compris.
 */
import { gunzipSync } from 'node:zlib';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { versEntierV4, versPrefixeV6 } from './geoip.mjs';

const MAGIC = 'RECOHEB1';
const TAILLE_BORNE_V6 = 6; // uint48 : un préfixe /48 tient sur six octets.

/** Le chemin par défaut : le dépôt entier est déployé, `src/` compris. */
export function cheminTable(cwd = process.cwd()) {
  return join(cwd, 'src', 'lib', 'audience', 'hebergeurs-ip.bin.gz');
}

/** L'état du chargement, mémorisé, y compris l'échec. */
let table = undefined;

/** Pour les tests : oublie la table chargée. */
export function reinitialiser() {
  table = undefined;
}

/**
 * Décode l'en-tête et repère les quatre colonnes.
 *
 * Rend `null` sur tout ce qui n'est pas exactement le format attendu : une
 * table d'une version future, ou tronquée par un transfert, désactive le
 * repère au lieu de le fausser.
 */
export function decoder(octets) {
  try {
    if (!octets || octets.length < 26) return null;
    const vue = new DataView(octets.buffer, octets.byteOffset, octets.byteLength);
    if (Buffer.from(octets.buffer, octets.byteOffset, 8).toString('ascii') !== MAGIC) {
      return null;
    }
    if (vue.getUint16(8) !== 1) return null;
    const edition = Buffer.from(octets.buffer, octets.byteOffset + 10, 8)
      .toString('ascii').trim();

    let pos = 18;
    const n4 = vue.getUint32(pos); pos += 4;
    const debuts4 = pos; pos += n4 * 4;
    const fins4 = pos; pos += n4 * 4;
    const n6 = vue.getUint32(pos); pos += 4;
    const debuts6 = pos; pos += n6 * TAILLE_BORNE_V6;
    const fins6 = pos; pos += n6 * TAILLE_BORNE_V6;

    // La longueur annoncée doit être la longueur réelle : sinon la recherche
    // binaire lirait au-delà du tampon.
    if (pos !== octets.byteLength) return null;
    return { vue, edition, n4, debuts4, fins4, n6, debuts6, fins6 };
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

/** L'édition de la table chargée, pour l'afficher, ou `null`. */
export function editionTable(chemin) {
  return chargee(chemin)?.edition ?? null;
}

/** uint48 gros-boutiste : deux octets de poids fort, puis quatre. */
const lire48 = (vue, p) => vue.getUint16(p) * 4294967296 + vue.getUint32(p + 2);

/** `valeur` tombe-t-elle dans une des plages ? Recherche du dernier début ≤ valeur. */
function dansUnePlage(n, lireDebut, lireFin, valeur) {
  let bas = 0;
  let haut = n - 1;
  let trouve = -1;
  while (bas <= haut) {
    const milieu = (bas + haut) >> 1;
    if (lireDebut(milieu) <= valeur) {
      trouve = milieu;
      bas = milieu + 1;
    } else {
      haut = milieu - 1;
    }
  }
  return trouve >= 0 && valeur <= lireFin(trouve);
}

/** Vrai si l'adresse est dans la table ; faux dans tous les autres cas. */
export function estHebergeur(ip, { chemin } = {}) {
  if (typeof ip !== 'string' || !ip) return false;
  const t = chargee(chemin);
  if (!t) return false;

  let adresse = ip.trim();
  // `::ffff:192.0.2.1` : une IPv4 vue à travers une pile IPv6 (socket en
  // double pile).
  const mappee = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(adresse);
  if (mappee) adresse = mappee[1];

  if (adresse.includes(':')) {
    const prefixe = versPrefixeV6(adresse);
    if (prefixe === null) return false;
    return dansUnePlage(
      t.n6,
      (i) => lire48(t.vue, t.debuts6 + i * TAILLE_BORNE_V6),
      (i) => lire48(t.vue, t.fins6 + i * TAILLE_BORNE_V6),
      prefixe,
    );
  }
  const entier = versEntierV4(adresse);
  if (entier === null) return false;
  return dansUnePlage(
    t.n4,
    (i) => t.vue.getUint32(t.debuts4 + i * 4),
    (i) => t.vue.getUint32(t.fins4 + i * 4),
    entier,
  );
}
