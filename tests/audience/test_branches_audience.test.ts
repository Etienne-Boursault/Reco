/**
 * Branches de défense de `src/lib/audience/*.mjs` qu'aucun autre test n'atteignait.
 *
 * Ajoutés avec AU-1 A (2026-11-27), quand `vitest.config.ts` a commencé à
 * mesurer `src/lib/audience/**` : ces fichiers n'étaient pas dans le périmètre
 * et leurs gardes (entrée absurde, journal absent) n'avaient jamais été
 * comptées.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { EventEmitter } from 'node:events';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { cheminSeul, langue, provenance } from '../../src/lib/audience/derive.mjs';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { decoder } from '../../src/lib/audience/geoip.mjs';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { adresseCliente, hoteDe, mesurerVisite, sourceDuChemin } from '../../src/lib/audience/mesure.mjs';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { enregistrer } from '../../src/lib/audience/storage.mjs';

afterEach(() => {
  (enregistrer as { _prevenu?: boolean })._prevenu = false;
});

describe('derive : entrées absurdes', () => {
  it('cheminSeul coupe la requête et refuse ce qui n’est pas un chemin', () => {
    expect(cheminSeul(undefined)).toBe('/');
    expect(cheminSeul('pas-un-chemin')).toBe('/');
    expect(cheminSeul('/a/b?x=1#ancre')).toBe('/a/b');
  });

  it('provenance rend null sans hôte', () => {
    expect(provenance('file:///tmp/x', 'unebonnere.co')).toBeNull();
  });

  it('langue rend null sur une valeur vide', () => {
    expect(langue(',fr')).toBeNull();
  });
});

describe('geoip : en-tête qui promet plus que le fichier', () => {
  it('decoder rend null quand les décomptes sortent du tampon', () => {
    const octets = Buffer.alloc(64);
    octets.write('RECOGEO1');
    octets.writeUInt16BE(1, 8);
    octets.writeUInt16BE(0, 18); // aucun pays
    octets.writeUInt32BE(0xffffffff, 20); // n4 démesuré
    expect(decoder(octets)).toBeNull();
  });
});

describe('mesure : requêtes incomplètes', () => {
  it('adresseCliente retombe sur le socket quand le suivi est vide', () => {
    expect(adresseCliente({ headers: { 'x-forwarded-for': ' , ' }, socket: { remoteAddress: '1.2.3.4' } })).toBe('1.2.3.4');
    expect(adresseCliente({})).toBeNull();
  });

  it('hoteDe rend null sans hôte exploitable', () => {
    expect(hoteDe('file:///tmp')).toBeNull();
  });

  it('sourceDuChemin tolère un chemin absent', () => {
    expect(sourceDuChemin(undefined, null)).toBe('_site');
    expect(sourceDuChemin('/sans-liste', null)).toBe('_site');
    expect(sourceDuChemin('/Mauvais', new Set(['Mauvais']))).toBe('_site');
  });

  it('mesurerVisite compte une requête sans url ni en-têtes', () => {
    const recus: unknown[] = [];
    const res = Object.assign(new EventEmitter(), { statusCode: 200 });
    const annuler = mesurerVisite({ method: 'GET' }, res, { ecrire: (e: unknown) => recus.push(e) });
    res.emit('finish');
    expect(recus).toHaveLength(1);
    annuler();
  });

  it('mesurerVisite ne plante pas si la réponse n’a pas de off', () => {
    const res = { once: () => {}, statusCode: 200 };
    const annuler = mesurerVisite({ url: '/', method: 'GET', headers: {} }, res, { ecrire: () => {} });
    expect(() => annuler()).not.toThrow();
  });
});

describe('storage : journal minimal', () => {
  it('survit à un journal sans warn et à une erreur sans message', () => {
    expect(enregistrer({ ts: 'pas-une-date' }, 'un-bon-moment', '/x\0', {})).toBe(false);
  });
});
