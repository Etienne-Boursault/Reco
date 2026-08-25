/**
 * Tests de `src/lib/audience/geoip.mjs` — le pays d'une adresse IP.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Ce module est sur le chemin de CHAQUE requête. Une exception y arrêterait le
 * site entier pour un chiffre secondaire ; c'est donc sa robustesse qui est
 * verrouillée ici en premier, avant sa justesse.
 *
 * Vient ensuite le décodage du format binaire : une table tronquée ou d'une
 * version future doit désactiver la mesure, jamais produire des pays au
 * hasard. Un mauvais pays est pire qu'un pays absent — il se lit comme une
 * information.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { gunzipSync, gzipSync } from 'node:zlib';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

// @ts-expect-error — module `.mjs` sans déclaration de types
import {
  cheminTable,
  decoder,
  editionTable,
  paysDeIP,
  reinitialiser,
  versEntierV4,
  versPrefixeV6,
} from '../../src/lib/audience/geoip.mjs';

afterEach(() => reinitialiser());

// ===== Lecture des adresses ================================================
describe('versEntierV4', () => {
  it('convertit les bornes de l’espace', () => {
    expect(versEntierV4('0.0.0.0')).toBe(0);
    expect(versEntierV4('255.255.255.255')).toBe(4294967295);
    expect(versEntierV4('8.8.8.8')).toBe(134744072);
  });

  it('refuse ce qui n’est pas une adresse', () => {
    // `Number(' 1')` vaut 1 et `Number('1e2')` vaut 100 : une conversion
    // permissive accepterait des chaînes qui ne sont pas des adresses.
    expect(versEntierV4('1.2.3')).toBeNull();
    expect(versEntierV4('1.2.3.4.5')).toBeNull();
    expect(versEntierV4('1.2.3.256')).toBeNull();
    expect(versEntierV4('1.2.3. 4')).toBeNull();
    expect(versEntierV4('1.2.3.1e2')).toBeNull();
    expect(versEntierV4('1.2.3.')).toBeNull();
  });
});

describe('versPrefixeV6', () => {
  it('garde les 48 premiers bits', () => {
    expect(versPrefixeV6('2a01:e0a:1:2::1')).toBe(0x2a01 * 65536 * 65536 + 0x0e0a * 65536 + 1);
  });

  it('développe la notation abrégée', () => {
    expect(versPrefixeV6('::1')).toBe(0);
    expect(versPrefixeV6('2001:db8::')).toBe(0x2001 * 65536 * 65536 + 0x0db8 * 65536);
    expect(versPrefixeV6('2001:db8:0:0:0:0:0:0')).toBe(versPrefixeV6('2001:db8::'));
  });

  it('reste exact malgré la virgule flottante', () => {
    // 48 bits tiennent dans un Number sans perte ; au-delà il aurait fallu un
    // BigInt, payé à chaque visite.
    expect(versPrefixeV6('ffff:ffff:ffff::')).toBe(281474976710655);
    expect(Number.isSafeInteger(versPrefixeV6('ffff:ffff:ffff::'))).toBe(true);
  });

  it('refuse ce qui n’est pas une adresse v6', () => {
    expect(versPrefixeV6('zz::')).toBeNull();
    expect(versPrefixeV6('1::2::3')).toBeNull();
    expect(versPrefixeV6('2001:db8')).toBeNull();
    expect(versPrefixeV6('::ffff:192.0.2.1')).toBeNull();
    expect(versPrefixeV6('2001:db8:0:0:0:0:0:0:0')).toBeNull();
  });
});

// ===== La table réelle =====================================================
describe('paysDeIP sur la table embarquée', () => {
  it('reconnaît des adresses de référence', () => {
    // Des attributions stables depuis des années. Si la mise à jour mensuelle
    // de la base les faisait bouger, c'est le test qui devrait être relu — pas
    // contourné.
    expect(paysDeIP('8.8.8.8')).toBe('US');
    expect(paysDeIP('213.186.33.5')).toBe('FR');
  });

  it('lit aussi l’IPv6', () => {
    // Une part importante du trafic mobile et des box arrive en v6 : sans
    // elle, ces visiteurs seraient tous « inconnus ».
    expect(paysDeIP('2a01:e0a:1:2::1')).toBe('FR');
    expect(paysDeIP('2600::')).toBe('US');
  });

  it('déplie une IPv4 vue à travers une pile v6', () => {
    // Node produit cette forme dès qu'un socket est en double pile.
    expect(paysDeIP('::ffff:8.8.8.8')).toBe('US');
    expect(paysDeIP('::FFFF:8.8.8.8')).toBe('US');
  });

  it('rend null sur une adresse privée plutôt qu’un pays inventé', () => {
    // La base les marque `ZZ` — « inconnu ». Le présenter comme un pays
    // ferait apparaître un territoire imaginaire dans le classement.
    expect(paysDeIP('127.0.0.1')).toBeNull();
    expect(paysDeIP('10.0.0.1')).toBeNull();
    expect(paysDeIP('192.168.1.1')).toBeNull();
  });

  it('expose l’édition chargée', () => {
    expect(editionTable()).toMatch(/^\d{4}-\d{2}$/);
  });
});

// ===== Robustesse ==========================================================
describe('robustesse', () => {
  it('ne lève jamais sur une entrée absurde', () => {
    // Ce module est sur le chemin de chaque requête : une exception ici
    // arrêterait le site pour un chiffre secondaire.
    for (const entree of [null, undefined, '', 42, {}, [], 'pas-une-ip', '...', ':::', 'a'.repeat(5000)]) {
      expect(() => paysDeIP(entree as never)).not.toThrow();
      expect(paysDeIP(entree as never)).toBeNull();
    }
  });

  it('tolère une table absente : un fork peut ne pas l’avoir construite', () => {
    reinitialiser();
    expect(paysDeIP('8.8.8.8', { chemin: '/introuvable/pays-ip.bin.gz' })).toBeNull();
  });

  it('ne relit pas le fichier à chaque appel', () => {
    // Réessayer d'ouvrir un fichier absent coûterait un appel système par
    // visite, pour le même résultat.
    reinitialiser();
    const absent = '/introuvable/pays-ip.bin.gz';
    expect(paysDeIP('8.8.8.8', { chemin: absent })).toBeNull();
    // Le second appel ne passe même plus le chemin : la décision est mémorisée.
    expect(paysDeIP('8.8.8.8')).toBeNull();
  });
});

// ===== Le décodage du format ===============================================
describe('decoder', () => {
  const vraie = () => readFileSync(cheminTable());

  function avecTable(octets: Buffer, fn: (chemin: string) => void) {
    const dossier = mkdtempSync(path.join(tmpdir(), 'reco-geoip-'));
    const chemin = path.join(dossier, 'pays-ip.bin.gz');
    writeFileSync(chemin, octets);
    try {
      reinitialiser();
      fn(chemin);
    } finally {
      rmSync(dossier, { recursive: true, force: true });
      reinitialiser();
    }
  }

  it('refuse un fichier qui n’est pas une table', () => {
    expect(decoder(Buffer.from('bonjour'))).toBeNull();
    expect(decoder(Buffer.alloc(64))).toBeNull();
    expect(decoder(null as never)).toBeNull();
  });

  it('refuse une version qu’il ne connaît pas', () => {
    // Une table produite par une version future n'est pas forcément lisible :
    // mieux vaut ne rien mesurer que mal mesurer.
    const brut = Buffer.concat([Buffer.from('RECOGEO1'), Buffer.alloc(64)]);
    brut.writeUInt16BE(2, 8);
    expect(decoder(brut)).toBeNull();
  });

  it('refuse une table tronquée', () => {
    // Sans ce contrôle, la recherche binaire lirait au-delà du tampon.
    const complet = gunzipSync(vraie());
    expect(decoder(complet)).not.toBeNull();
    expect(decoder(complet.subarray(0, complet.length - 1))).toBeNull();
  });

  it('refuse une table plus longue que ce qu’elle annonce', () => {
    const complet = gunzipSync(vraie());
    expect(decoder(Buffer.concat([complet, Buffer.alloc(1)]))).toBeNull();
  });

  it('désactive la mesure quand le fichier n’est pas du gzip', () => {
    avecTable(Buffer.from('ceci n’est pas du gzip'), (chemin) => {
      expect(paysDeIP('8.8.8.8', { chemin })).toBeNull();
    });
  });

  it('désactive la mesure quand le contenu est corrompu', () => {
    avecTable(gzipSync(Buffer.from('RECOGEO1 mais rien derrière')), (chemin) => {
      expect(paysDeIP('8.8.8.8', { chemin })).toBeNull();
    });
  });
});
