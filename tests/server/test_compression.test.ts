/**
 * Tests de `src/server/compression.mjs`.
 *
 * CE QUE CES TESTS DÉFENDENT
 * --------------------------
 * La première version de cette enveloppe était INERTE sur les routes à la
 * demande, et l'a été sans que rien ne le signale. Elle décidait de compresser
 * ainsi :
 *
 *     res.writeHead = (code, ...reste) => {
 *       const type = res.getHeader('Content-Type') || '';   // ← toujours vide
 *
 * Or le cœur d'Astro écrit ses réponses en passant les en-têtes EN ARGUMENT
 * (`core/app/node.js` : `destination.writeHead(status, createOutgoingHttpHeaders(headers))`),
 * jamais par `setHeader`. Au moment du test, `getHeader('Content-Type')`
 * renvoyait donc `undefined`, la condition était fausse, et pas un octet
 * n'était compressé — dans un fichier écrit POUR compresser.
 *
 * D'où la forme de ces tests : le faux gestionnaire ci-dessous écrit
 * exactement comme Astro. C'est la convention d'appel qui est testée, pas
 * seulement le résultat.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import http from 'node:http';
import { gunzipSync } from 'node:zlib';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { envelopper, accepteGzip, normaliserEntetes, lireEntete, fusionnerVary } from '../../src/server/compression.mjs';
import { demander, demarrer } from './_client';

const LONG = 'Le vent se lève, il faut tenter de vivre. '.repeat(80); // ≈ 3,3 Ko

type Ecriture = (req: http.IncomingMessage, res: http.ServerResponse) => void;

let arreterCourant: (() => Promise<void>) | null = null;

afterEach(async () => {
  if (arreterCourant) await arreterCourant();
  arreterCourant = null;
});

/** Monte un serveur dont TOUTES les réponses passent par l'enveloppe. */
async function monter(ecrire: Ecriture): Promise<number> {
  const serveur = http.createServer((req, res) => ecrire(req, envelopper(req, res)));
  const { port, arreter } = await demarrer(serveur);
  arreterCourant = arreter;
  return port;
}

/** Écrit à la manière d'Astro : en-têtes passés EN ARGUMENT de `writeHead`. */
const commeAstro = (corps: string, type = 'text/html; charset=utf-8'): Ecriture =>
  (_req, res) => {
    res.writeHead(200, {
      'Content-Type': type,
      'Content-Length': Buffer.byteLength(corps),
    });
    res.end(corps);
  };

// ---------------------------------------------------------------------------
// Le cas qui a échappé à la première version
// ---------------------------------------------------------------------------
describe('envelopper — en-têtes passés en argument (convention d’Astro)', () => {
  it('COMPRESSE une réponse dont le type n’est connu qu’à writeHead', async () => {
    const port = await monter(commeAstro(LONG));
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });

    expect(r.entetes['content-encoding']).toBe('gzip');
    // Le corps doit être RÉELLEMENT du gzip, et se relire à l'identique.
    expect(gunzipSync(r.brut).toString('utf-8')).toBe(LONG);
    // Et il doit vraiment peser moins lourd : sans quoi tout ceci ne sert à rien.
    expect(r.brut.length).toBeLessThan(Buffer.byteLength(LONG) / 2);
  });

  it('RETIRE le Content-Length du clair — sinon la réponse est tronquée', async () => {
    // C'est le bug le plus vicieux du genre : le navigateur lit N octets
    // annoncés alors que le corps compressé en fait beaucoup moins, et la page
    // reste en chargement perpétuel.
    const port = await monter(commeAstro(LONG));
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-length']).toBeUndefined();
  });

  it('pose Vary: Accept-Encoding', async () => {
    const port = await monter(commeAstro(LONG));
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(String(r.entetes.vary)).toMatch(/accept-encoding/i);
  });

  it('CONSERVE un Vary déjà posé au lieu de l’écraser', async () => {
    const port = await monter((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html', Vary: 'Cookie', 'Content-Length': Buffer.byteLength(LONG) });
      res.end(LONG);
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(String(r.entetes.vary)).toMatch(/cookie/i);
    expect(String(r.entetes.vary)).toMatch(/accept-encoding/i);
  });
});

// ---------------------------------------------------------------------------
// Les refus de compresser
// ---------------------------------------------------------------------------
describe('envelopper — quand il ne FAUT pas compresser', () => {
  it('client sans gzip → corps en clair, intact', async () => {
    const port = await monter(commeAstro(LONG));
    const r = await demander(port, '/');
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(r.brut.toString('utf-8')).toBe(LONG);
  });

  it('réponse trop courte → non compressée (l’en-tête coûterait plus)', async () => {
    const court = 'court';
    const port = await monter(commeAstro(court));
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(r.texte).toBe(court);
  });

  it('type non compressible → laissé tel quel', async () => {
    const port = await monter(commeAstro(LONG, 'image/png'));
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
  });

  it('réponse DÉJÀ encodée → pas de double compression', async () => {
    const port = await monter((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/html', 'Content-Encoding': 'br' });
      res.end('déjà compressé ailleurs');
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBe('br');
  });

  it('304 → aucun corps, aucune compression', async () => {
    // Compresser une réponse sans corps produit un flux gzip vide de 20 octets
    // sur une réponse qui doit en faire ZÉRO : les clients raccrochent.
    const port = await monter((_req, res) => {
      res.writeHead(304, { 'Content-Type': 'text/html' });
      res.end();
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.statut).toBe(304);
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(r.brut.length).toBe(0);
  });

  it('HEAD → en-têtes seuls, sans corps compressé', async () => {
    const port = await monter(commeAstro(LONG));
    const r = await demander(port, '/', { methode: 'HEAD', entetes: { 'accept-encoding': 'gzip' } });
    expect(r.brut.length).toBe(0);
    expect(r.entetes['content-encoding']).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Les formes d'appel de `writeHead` et `end`
// ---------------------------------------------------------------------------
describe('envelopper — formes d’appel tolérées', () => {
  it('writeHead(code, message, entetes) — message de statut conservé', async () => {
    const port = await monter((_req, res) => {
      res.writeHead(201, 'Créé', { 'Content-Type': 'text/plain', 'Content-Length': Buffer.byteLength(LONG) });
      res.end(LONG);
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.statut).toBe(201);
    expect(r.entetes['content-encoding']).toBe('gzip');
    expect(r.texte).toBe(LONG);
  });

  it('writeHead(code) seul, en-têtes posés par setHeader', async () => {
    const port = await monter((_req, res) => {
      res.setHeader('Content-Type', 'text/plain; charset=utf-8');
      res.writeHead(200);
      res.end(LONG);
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBe('gzip');
    expect(r.texte).toBe(LONG);
  });

  it('res.end(rappel) — le rappel est une FONCTION, pas un corps', async () => {
    // `if (chunk) gz.write(chunk)` faisait exploser gzip sur cette forme :
    // « The "chunk" argument must be of type string or Buffer ».
    let rappelAppele = false;
    const port = await monter((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.write(LONG);
      res.end(() => { rappelAppele = true; });
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.texte).toBe(LONG);
    expect(rappelAppele).toBe(true);
  });

  it('écriture en plusieurs morceaux → corps recomposé à l’identique', async () => {
    const port = await monter((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      for (let i = 0; i < 40; i += 1) res.write(`morceau ${i} — ${LONG.slice(0, 120)}\n`);
      res.end();
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBe('gzip');
    expect(r.texte.split('\n').filter(Boolean)).toHaveLength(40);
    expect(r.texte).toContain('morceau 39');
  });

  it('res.end(corps, rappel) — rappel en SECONDE position', async () => {
    let rappelAppele = false;
    const port = await monter((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      (res.end as (c: string, r: () => void) => void)(LONG, () => { rappelAppele = true; });
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.texte).toBe(LONG);
    expect(rappelAppele).toBe(true);
  });

  it('AUCUN Content-Type nulle part → pas de compression, pas d’erreur', async () => {
    // Ni en argument, ni par `setHeader` : le type effectif est la chaîne
    // vide. Compresser à l'aveugle un contenu de type inconnu reviendrait à
    // parier qu'il est textuel.
    const port = await monter((_req, res) => {
      res.writeHead(200);
      res.end(LONG);
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(r.texte).toBe(LONG);
  });

  it('res.write reste utilisable quand la réponse n’est PAS compressée', async () => {
    // L'enveloppe remplace `write` dans TOUS les cas, y compris lorsqu'elle
    // décide de ne rien compresser : le chemin de repli doit donc écrire
    // normalement, sinon aucune image ne serait plus servie.
    const port = await monter((_req, res) => {
      res.writeHead(200, { 'Content-Type': 'image/png' });
      res.write('un');
      res.write('deux');
      res.end();
    });
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(r.texte).toBe('undeux');
  });

  it('accents et caractères multi-octets traversés sans dégât', async () => {
    const accentue = 'Où sont les neiges d’antan ? — « çàé » 🎧 '.repeat(60);
    const port = await monter(commeAstro(accentue, 'text/plain; charset=utf-8'));
    const r = await demander(port, '/', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.texte).toBe(accentue);
  });
});

// ---------------------------------------------------------------------------
// Les protections : erreur du compresseur, contre-pression, client parti
// ---------------------------------------------------------------------------
describe('envelopper — protections contre l’arrêt du processus', () => {
  /**
   * Faux `res` minimal, pour observer ce qu'on ne peut pas provoquer depuis un
   * vrai client : le moment où la socket sature, et celui où elle se ferme.
   */
  function fauxRes(retourDeWrite: boolean) {
    const ecrits: unknown[] = [];
    const ecouteurs: Record<string, Array<(...a: unknown[]) => void>> = {};
    return {
      ecrits,
      ecouteurs,
      detruit: false,
      getHeader: () => undefined,
      setHeader: () => {},
      removeHeader: () => {},
      writeHead: () => {},
      write: (morceau: unknown) => { ecrits.push(morceau); return retourDeWrite; },
      end: () => {},
      destroy(this: { detruit: boolean }) { this.detruit = true; },
      on(this: any, evenement: string, f: (...a: unknown[]) => void) {
        (ecouteurs[evenement] ||= []).push(f);
        return this;
      },
      once(this: any, evenement: string, f: (...a: unknown[]) => void) {
        return this.on(evenement, f);
      },
      emettre(evenement: string) {
        for (const f of ecouteurs[evenement] ?? []) f();
      },
    };
  }

  const reqGzip = { method: 'GET', headers: { 'accept-encoding': 'gzip' } } as any;

  /**
   * Attend que le compresseur ait RÉELLEMENT produit des octets.
   *
   * zlib travaille sur le pool de threads : un simple `setImmediate` revient
   * avant que le moindre octet ne soit sorti, et l'assertion mesurerait alors
   * l'ordonnancement plutôt que le comportement.
   */
  async function attendreEcriture(res: { ecrits: unknown[] }) {
    for (let essai = 0; essai < 200 && res.ecrits.length === 0; essai += 1) {
      await new Promise((r) => setTimeout(r, 5));
    }
    expect(res.ecrits.length).toBeGreaterThan(0);
  }

  it('une erreur du compresseur COUPE la réponse au lieu de tuer le processus', async () => {
    // Sans écouteur `error`, Node relaie l'événement en exception non captée :
    // le processus s'arrête, et le site entier tombe pour une seule requête.
    const { createGzip } = await import('node:zlib');
    const gz = createGzip();
    const res = fauxRes(true);

    envelopper(reqGzip, res as any, { creerCompresseur: () => gz });
    res.writeHead(200, { 'Content-Type': 'text/html' });
    gz.emit('error', new Error('boum'));

    expect(res.detruit).toBe(true);
  });

  it('met le compresseur en PAUSE quand la socket sature, et le relance au drain', async () => {
    // C'est ce qui empêche un gros document de se recopier intégralement en
    // mémoire quand le client lit lentement.
    const { createGzip } = await import('node:zlib');
    const gz = createGzip({ level: 6 });
    const pause = vi.spyOn(gz, 'pause');
    const resume = vi.spyOn(gz, 'resume');
    const res = fauxRes(false);          // la socket refuse : write renvoie false

    envelopper(reqGzip, res as any, { creerCompresseur: () => gz });
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.write('x'.repeat(50_000));
    res.end();
    await attendreEcriture(res);

    expect(pause).toHaveBeenCalled();
    // On compare un DELTA, pas un absolu : attacher `on('data')` fait appeler
    // `resume()` par Node lui-même, et une assertion « jamais appelé » mesure
    // alors la plomberie du flux au lieu de notre reprise après drain.
    const avantDrain = resume.mock.calls.length;
    res.emettre('drain');
    expect(resume.mock.calls.length).toBe(avantDrain + 1);
  });

  it('ne met PAS en pause quand la socket suit', async () => {
    const { createGzip } = await import('node:zlib');
    const gz = createGzip({ level: 6 });
    const pause = vi.spyOn(gz, 'pause');
    const res = fauxRes(true);

    envelopper(reqGzip, res as any, { creerCompresseur: () => gz });
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.write('x'.repeat(50_000));
    res.end();
    await attendreEcriture(res);

    expect(pause).not.toHaveBeenCalled();
  });

  it('client parti en cours de route → le compresseur est libéré', async () => {
    const { createGzip } = await import('node:zlib');
    const gz = createGzip();
    const res = fauxRes(true);

    envelopper(reqGzip, res as any, { creerCompresseur: () => gz });
    res.writeHead(200, { 'Content-Type': 'text/html' });
    expect(gz.destroyed).toBe(false);

    res.emettre('close');
    expect(gz.destroyed).toBe(true);
  });

  it('réponse NON compressée : la fermeture ne réveille aucun compresseur', () => {
    // `gz` vaut `null` : le `?.` est ce qui évite un TypeError à chaque fin de
    // réponse non compressée — c'est-à-dire tout le temps.
    const res = fauxRes(true);
    envelopper(reqGzip, res as any);
    res.writeHead(200, { 'Content-Type': 'image/png' });
    expect(() => res.emettre('close')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Les fonctions pures
// ---------------------------------------------------------------------------
describe('accepteGzip', () => {
  const faux = (valeur?: string) => ({ headers: valeur === undefined ? {} : { 'accept-encoding': valeur } });

  it.each([
    ['gzip', true],
    ['gzip, deflate, br', true],
    ['deflate', false],
    ['', false],
    [undefined, false],
    // Le piège : « x-gzip » ou « notgzip » ne sont PAS gzip. La limite de mot
    // (`\b`) est ce qui les écarte.
    ['notgzip', false],
  ])('« %s » → %s', (valeur, attendu) => {
    expect(accepteGzip(faux(valeur as string | undefined))).toBe(attendu);
  });
});

describe('normaliserEntetes', () => {
  it('objet simple', () => {
    expect(normaliserEntetes([{ 'Content-Type': 'text/html' }]))
      .toEqual({ message: undefined, entetes: { 'Content-Type': 'text/html' } });
  });

  it('message de statut puis objet', () => {
    const { message, entetes } = normaliserEntetes(['OK', { A: '1' }]);
    expect(message).toBe('OK');
    expect(entetes).toEqual({ A: '1' });
  });

  it('tableau plat [clé, valeur, clé, valeur]', () => {
    expect(normaliserEntetes([['A', '1', 'B', '2']]).entetes).toEqual({ A: '1', B: '2' });
  });

  it('tableau de paires [[clé, valeur], …]', () => {
    expect(normaliserEntetes([[['A', '1'], ['B', '2']]]).entetes).toEqual({ A: '1', B: '2' });
  });

  it('aucun en-tête → objet vide, jamais null', () => {
    expect(normaliserEntetes([]).entetes).toEqual({});
    expect(normaliserEntetes([undefined]).entetes).toEqual({});
  });

  it('renvoie une copie MODIFIABLE, sans toucher à l’original', () => {
    const original = { 'Content-Length': '10' };
    const { entetes } = normaliserEntetes([original]);
    delete entetes['Content-Length'];
    expect(original['Content-Length']).toBe('10');
  });
});

describe('fusionnerVary', () => {
  it('ajoute Accept-Encoding à un Vary existant', () => {
    expect(fusionnerVary('Cookie')).toBe('Cookie, Accept-Encoding');
  });

  it('ne le DOUBLE pas s’il est déjà annoncé', () => {
    // Un `Vary: Accept-Encoding, Accept-Encoding` n'est pas fatal, mais il
    // trahit une manipulation à l'aveugle et grossit chaque réponse.
    expect(fusionnerVary('Accept-Encoding')).toBe('Accept-Encoding');
  });

  it('reconnaît une casse différente', () => {
    expect(fusionnerVary('accept-encoding, Cookie')).toBe('accept-encoding, Cookie');
  });

  it('vide ou absent → Accept-Encoding seul', () => {
    expect(fusionnerVary('')).toBe('Accept-Encoding');
    expect(fusionnerVary(undefined)).toBe('Accept-Encoding');
  });

  it('nettoie les espaces et les entrées vides', () => {
    expect(fusionnerVary(' Cookie ,, ')).toBe('Cookie, Accept-Encoding');
  });
});

describe('lireEntete — insensible à la casse', () => {
  it.each(['content-type', 'Content-Type', 'CONTENT-TYPE'])('trouve via « %s »', (nom) => {
    expect(lireEntete({ 'CoNtEnT-TyPe': 'text/html' }, nom)).toBe('text/html');
  });

  it('absent → undefined', () => {
    expect(lireEntete({ A: '1' }, 'content-type')).toBeUndefined();
  });
});
