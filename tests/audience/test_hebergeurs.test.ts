/**
 * Tests de `src/lib/audience/hebergeurs.mjs` : cette adresse appartient-elle à
 * un hébergeur ? (AU-1 A, 2026-11-27)
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Comme `geoip.mjs`, ce module est sur le chemin de CHAQUE requête : il ne
 * doit jamais lever. Table absente, illisible, tronquée, adresse absurde : la
 * réponse est `false`, et la page continue de s'afficher.
 *
 * Le second risque est l'inverse de celui du pays : classer un visiteur réel
 * en « hébergeur » le fait sortir du compte sans que personne le voie. Les
 * réseaux de vrais visiteurs (R-8 : WARP, iCloud Private Relay) sont donc
 * vérifiés sur la table réelle.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { gunzipSync, gzipSync } from 'node:zlib';
import { mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

// @ts-expect-error — module `.mjs` sans déclaration de types
import {
  cheminTable,
  decoder,
  editionTable,
  estHebergeur,
  reinitialiser,
} from '../../src/lib/audience/hebergeurs.mjs';

afterEach(() => reinitialiser());

/** Une table RECOHEB1 minuscule, pour viser les bornes et les trous. */
function fabriquer(v4: [number, number][], v6: [number, number][]): Buffer {
  const u32 = (n: number) => {
    const b = Buffer.alloc(4);
    b.writeUInt32BE(n);
    return b;
  };
  const u48 = (n: number) => {
    const b = Buffer.alloc(6);
    b.writeUIntBE(n, 0, 6);
    return b;
  };
  const entete = Buffer.alloc(10);
  entete.write('RECOHEB1');
  entete.writeUInt16BE(1, 8);
  return Buffer.concat([
    entete,
    Buffer.from('2026-11 '),
    u32(v4.length),
    ...v4.map(([d]) => u32(d)),
    ...v4.map(([, f]) => u32(f)),
    u32(v6.length),
    ...v6.map(([d]) => u48(d)),
    ...v6.map(([, f]) => u48(f)),
  ]);
}

/** Écrit une table dans un dossier jetable, le temps de `fn`. */
function avecTable(octets: Buffer, fn: (chemin: string) => void) {
  const dossier = mkdtempSync(path.join(tmpdir(), 'reco-heb-'));
  const chemin = path.join(dossier, 'hebergeurs-ip.bin.gz');
  writeFileSync(chemin, octets);
  try {
    reinitialiser();
    fn(chemin);
  } finally {
    rmSync(dossier, { recursive: true, force: true });
    reinitialiser();
  }
}

const V4: [number, number][] = [
  [0x0a000000, 0x0a0000ff], // 10.0.0.0 - 10.0.0.255
  [0x0a000300, 0x0a0003ff], // 10.0.3.0 - 10.0.3.255 (un trou avant)
];
const P6 = 0x2001_0db8_0001; // préfixe /48 de 2001:db8:1::/48

// ===== Bornes et trous =====================================================
describe('estHebergeur sur une petite table', () => {
  const table = gzipSync(fabriquer(V4, [[P6, P6 + 1]]));

  it('compte les bornes comprises, pas le trou ni les voisins', () => {
    avecTable(table, (chemin) => {
      const est = (ip: string) => estHebergeur(ip, { chemin });
      expect(est('10.0.0.0')).toBe(true);
      expect(est('10.0.0.255')).toBe(true);
      expect(est('10.0.1.0')).toBe(false); // juste après la fin
      expect(est('10.0.2.255')).toBe(false); // dans le trou
      expect(est('10.0.3.0')).toBe(true);
      expect(est('10.0.3.255')).toBe(true);
      expect(est('10.0.4.0')).toBe(false);
      expect(est('9.255.255.255')).toBe(false); // avant la première plage
    });
  });

  it('lit l’IPv6 au préfixe /48', () => {
    avecTable(table, (chemin) => {
      const est = (ip: string) => estHebergeur(ip, { chemin });
      expect(est('2001:db8:1::1')).toBe(true);
      expect(est('2001:db8:1:ffff:ffff:ffff:ffff:ffff')).toBe(true);
      expect(est('2001:db8:2::1')).toBe(true); // fin comprise
      expect(est('2001:db8:3::1')).toBe(false);
      expect(est('2001:db8::1')).toBe(false); // avant le début
    });
  });

  it('déplie une IPv4 vue à travers une pile v6', () => {
    avecTable(table, (chemin) => {
      expect(estHebergeur('::ffff:10.0.0.7', { chemin })).toBe(true);
      expect(estHebergeur('::FFFF:10.0.1.7', { chemin })).toBe(false);
    });
  });

  it('accepte les espaces autour de l’adresse', () => {
    avecTable(table, (chemin) => {
      expect(estHebergeur(' 10.0.0.7 ', { chemin })).toBe(true);
    });
  });

  it('rend false sur une adresse incompréhensible, sans lever', () => {
    avecTable(table, (chemin) => {
      for (const ip of ['10.0.0', '1.2.3.999', 'zz::', '1::2::3', '::ffff:1.2.3', 'pas-une-ip']) {
        expect(estHebergeur(ip, { chemin })).toBe(false);
      }
    });
  });

  it('lit la table UNE seule fois', () => {
    // Le fichier est supprimé après le premier appel : une seconde lecture
    // ferait passer la réponse à `false`.
    avecTable(table, (chemin) => {
      expect(estHebergeur('10.0.0.7', { chemin })).toBe(true);
      unlinkSync(chemin);
      expect(estHebergeur('10.0.0.8', { chemin })).toBe(true);
    });
  });

  it('expose l’édition', () => {
    avecTable(table, (chemin) => {
      expect(editionTable(chemin)).toBe('2026-11');
    });
  });
});

// ===== Robustesse ==========================================================
describe('robustesse', () => {
  it('ne lève jamais sur une entrée absurde', () => {
    for (const entree of [null, undefined, '', 42, {}, [], 'a'.repeat(5000)]) {
      expect(() => estHebergeur(entree as never)).not.toThrow();
      expect(estHebergeur(entree as never)).toBe(false);
    }
  });

  it('tolère une table absente et ne réessaie pas', () => {
    reinitialiser();
    expect(estHebergeur('10.0.0.7', { chemin: '/introuvable/h.bin.gz' })).toBe(false);
    expect(estHebergeur('10.0.0.7')).toBe(false); // décision mémorisée
    expect(editionTable()).toBeNull();
  });

  it('désactive le repère quand le fichier n’est pas du gzip', () => {
    avecTable(Buffer.from('ceci n’est pas du gzip'), (chemin) => {
      expect(estHebergeur('10.0.0.7', { chemin })).toBe(false);
    });
  });

  it('désactive le repère quand le contenu est corrompu', () => {
    avecTable(gzipSync(Buffer.from('RECOHEB1 mais rien derrière')), (chemin) => {
      expect(estHebergeur('10.0.0.7', { chemin })).toBe(false);
    });
  });
});

// ===== Le décodage du format ===============================================
describe('decoder', () => {
  const complet = fabriquer(V4, [[P6, P6 + 1]]);

  it('accepte une table complète', () => {
    expect(decoder(complet)).not.toBeNull();
    expect(decoder(fabriquer([], []))).not.toBeNull();
  });

  it('refuse ce qui n’est pas une table', () => {
    expect(decoder(Buffer.from('bonjour'))).toBeNull();
    expect(decoder(Buffer.alloc(64))).toBeNull();
    expect(decoder(null as never)).toBeNull();
  });

  it('refuse une table de la mauvaise famille (pays)', () => {
    const faux = Buffer.from(complet);
    faux.write('RECOGEO1');
    expect(decoder(faux)).toBeNull();
  });

  it('refuse une version inconnue', () => {
    const futur = Buffer.from(complet);
    futur.writeUInt16BE(2, 8);
    expect(decoder(futur)).toBeNull();
  });

  it('refuse une table dont le nombre de plages dépasse le fichier', () => {
    // 0xFFFFFFFF plages annoncées : la lecture de la suite sortirait du tampon.
    const gonfle = Buffer.from(complet);
    gonfle.writeUInt32BE(0xffffffff, 18);
    expect(decoder(gonfle)).toBeNull();
  });

  it('refuse une table tronquée ou trop longue', () => {
    // Sans ce contrôle, la recherche binaire lirait au-delà du tampon.
    expect(decoder(complet.subarray(0, complet.length - 1))).toBeNull();
    expect(decoder(Buffer.concat([complet, Buffer.alloc(1)]))).toBeNull();
  });
});

// ===== La table réelle =====================================================
describe('la table embarquée', () => {
  it('reconnaît des hébergeurs connus', () => {
    // Des attributions stables depuis des années : si la mise à jour de la
    // table les faisait bouger, c'est le test qui serait à relire.
    expect(estHebergeur('2.28.0.1')).toBe(true); // Hetzner
    expect(estHebergeur('1.44.96.1')).toBe(true); // Amazon
    expect(estHebergeur('165.227.1.1')).toBe(true); // DigitalOcean
    expect(estHebergeur('2001:67c:267c::1')).toBe(true);
  });

  it('R-8 : ne classe PAS les réseaux de vrais visiteurs en hébergeur', () => {
    expect(estHebergeur('1.1.1.1')).toBe(false); // Cloudflare (WARP)
    expect(estHebergeur('2.16.0.1')).toBe(false); // Akamai
    expect(estHebergeur('172.224.226.1')).toBe(false); // iCloud Private Relay
  });

  it('laisse passer des abonnés d’opérateurs', () => {
    expect(estHebergeur('90.1.2.3')).toBe(false);
    expect(estHebergeur('2a01:e0a:1:2::1')).toBe(false);
  });

  it('rend false sur une adresse privée', () => {
    for (const ip of ['127.0.0.1', '10.0.0.1', '192.168.1.1', '::1']) {
      expect(estHebergeur(ip)).toBe(false);
    }
  });

  it('expose l’édition chargée et pèse moins de 1 Mo', () => {
    expect(editionTable()).toMatch(/^\d{4}-\d{2}$/);
    expect(readFileSync(cheminTable()).length).toBeLessThan(1_000_000);
    expect(decoder(gunzipSync(readFileSync(cheminTable())))).not.toBeNull();
  });
});
