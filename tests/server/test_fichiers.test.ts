/**
 * Tests de `src/server/fichiers.mjs` — le service des fichiers construits.
 *
 * Deux familles distinctes, et il ne faut pas les confondre :
 *
 *   - la RÉSOLUTION du chemin, où se joue la sécurité. `fichierPour` est la
 *     seule chose qui empêche ce serveur d'exposer le disque entier ; elle est
 *     donc éprouvée par des attaques concrètes, pas par un test symbolique ;
 *   - le SERVICE, où se jouent le cache et la compression.
 *
 * Les fixtures sont écrites dans un dossier temporaire réel plutôt que
 * simulées : la traversée de répertoire dépend du système de fichiers (`\` est
 * un séparateur sous Windows et un caractère ordinaire sous Linux), et un faux
 * `fs` masquerait précisément la différence qu'on veut couvrir.
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import http from 'node:http';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { PassThrough } from 'node:stream';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { fichierPour, servirFichier, empreinte, politiqueCache, TYPES } from '../../src/server/fichiers.mjs';
import { demander, demarrer } from './_client';

const LONG = 'Sous le pont Mirabeau coule la Seine. '.repeat(80); // ≈ 3 Ko

let racine: string;
let arreterCourant: (() => Promise<void>) | null = null;

beforeAll(() => {
  racine = mkdtempSync(path.join(tmpdir(), 'reco-serveur-'));
  writeFileSync(path.join(racine, 'index.html'), `<!doctype html><p>${LONG}</p>`);
  writeFileSync(path.join(racine, 'petit.html'), '<p>ok</p>');
  writeFileSync(path.join(racine, 'image.png'), Buffer.alloc(4096, 7));
  mkdirSync(path.join(racine, '_astro'));
  writeFileSync(path.join(racine, '_astro', 'app.abc123.css'), `body{}/*${LONG}*/`);
  mkdirSync(path.join(racine, 'a-propos'));
  writeFileSync(path.join(racine, 'a-propos', 'index.html'), '<p>à propos</p>');
  // Le secret que la traversée de répertoire chercherait à atteindre : il est
  // posé À CÔTÉ de la racine, exactement là où `../` mènerait.
  writeFileSync(path.join(racine, '..', 'reco-secret-test.txt'), 'MOT_DE_PASSE');
});

afterAll(() => {
  rmSync(racine, { recursive: true, force: true });
  rmSync(path.join(racine, '..', 'reco-secret-test.txt'), { force: true });
});

afterEach(async () => {
  if (arreterCourant) await arreterCourant();
  arreterCourant = null;
});

/** Monte un serveur qui ne fait QUE servir le statique. */
async function monter(): Promise<number> {
  const serveur = http.createServer((req, res) => {
    const chemin = fichierPour(racine, req.url || '/');
    if (!chemin) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      return res.end('rien');
    }
    return servirFichier(req, res, chemin);
  });
  const { port, arreter } = await demarrer(serveur);
  arreterCourant = arreter;
  return port;
}

// ---------------------------------------------------------------------------
// Sécurité : la traversée de répertoire
// ---------------------------------------------------------------------------
describe('fichierPour — traversée de répertoire', () => {
  it.each([
    ['remontée simple', '/../reco-secret-test.txt'],
    ['remontée multiple', '/../../../../../../etc/passwd'],
    ['remontée après un segment valide', '/a-propos/../../reco-secret-test.txt'],
    ['remontée encodée', '/%2e%2e/reco-secret-test.txt'],
    ['remontée doublement encodée dans le nom', '/%2e%2e%2freco-secret-test.txt'],
    ['antislash', '/..\\reco-secret-test.txt'],
    ['antislash encodé', '/..%5creco-secret-test.txt'],
    ['barre obliques multiples', '//../reco-secret-test.txt'],
  ])('refuse : %s', (_nom, url) => {
    expect(fichierPour(racine, url)).toBeNull();
  });

  it('le secret est bien LÀ — sans quoi les tests ci-dessus ne prouvent rien', () => {
    // Garde-fou contre le test qui se félicite d'un refus alors que la cible
    // n'existait pas : ici on vérifie que le fichier convoité existe vraiment
    // et qu'il est atteignable en partant de la racine du disque.
    expect(fichierPour(path.resolve(racine, '..'), '/reco-secret-test.txt')).not.toBeNull();
  });

  it('refuse un pourcentage mal formé au lieu de lever', () => {
    expect(fichierPour(racine, '/%zz')).toBeNull();
  });

  it('refuse un octet nul (troncature de chemin)', () => {
    expect(fichierPour(racine, '/index.html\0.txt')).toBeNull();
  });

  it('refuse un nom démesuré sans lever', () => {
    expect(fichierPour(racine, `/${'a'.repeat(5000)}`)).toBeNull();
  });
});

describe('fichierPour — résolution normale', () => {
  it('trouve un fichier', () => {
    expect(fichierPour(racine, '/petit.html')).toBe(path.join(racine, 'petit.html'));
  });

  it('la racine mène à index.html', () => {
    expect(fichierPour(racine, '/')).toBe(path.join(racine, 'index.html'));
  });

  it('un dossier mène à son index.html', () => {
    expect(fichierPour(racine, '/a-propos')).toBe(path.join(racine, 'a-propos', 'index.html'));
  });

  it('ignore la chaîne de requête', () => {
    expect(fichierPour(racine, '/petit.html?v=2')).toBe(path.join(racine, 'petit.html'));
  });

  it('décode les caractères échappés du nom', () => {
    writeFileSync(path.join(racine, 'été à Paris.txt'), 'ok');
    expect(fichierPour(racine, '/%C3%A9t%C3%A9%20%C3%A0%20Paris.txt'))
      .toBe(path.join(racine, 'été à Paris.txt'));
  });

  it('un fichier absent → null', () => {
    expect(fichierPour(racine, '/fantome.html')).toBeNull();
  });

  it('un segment APRÈS un fichier → null', () => {
    expect(fichierPour(racine, '/index.html/en-plus')).toBeNull();
  });

  it('une sonde qui LÈVE (ENOTDIR sous Linux) donne null, pas une exception', () => {
    // Sous Linux, `/index.html/en-plus` fait lever `statSync` avec ENOTDIR ;
    // sous Windows, la même URL ramène simplement « absent ». Le comportement
    // testé ici est donc simulé, faute de quoi il ne serait vérifié que sur
    // une plateforme sur deux — et le `catch` sauterait au premier nettoyage.
    const sondeQuiLeve = () => {
      const erreur = new Error('ENOTDIR: not a directory');
      (erreur as NodeJS.ErrnoException).code = 'ENOTDIR';
      throw erreur;
    };
    expect(fichierPour(racine, '/index.html/en-plus', { stat: sondeQuiLeve })).toBeNull();
  });

  it('un DOSSIER sans index.html → null (jamais de listing)', () => {
    mkdirSync(path.join(racine, 'vide'), { recursive: true });
    expect(fichierPour(racine, '/vide')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Cache et requêtes conditionnelles
// ---------------------------------------------------------------------------
describe('politiqueCache', () => {
  it('un fichier empreinté de _astro/ est immuable un an', () => {
    expect(politiqueCache(path.join(racine, '_astro', 'app.abc123.css')))
      .toBe('public, max-age=31536000, immutable');
  });

  it('une page HTML est revalidée', () => {
    expect(politiqueCache(path.join(racine, 'index.html')))
      .toBe('public, max-age=0, must-revalidate');
  });

  it('« _astro » dans un nom de fichier ne suffit PAS', () => {
    // La garde porte sur un SEGMENT de chemin, pas sur une sous-chaîne : sinon
    // « mon_astro_perso.html » hériterait d'un an de cache immuable.
    expect(politiqueCache(path.join(racine, 'mon_astro_perso.html')))
      .toBe('public, max-age=0, must-revalidate');
  });
});

describe('empreinte', () => {
  it('change quand la taille change', () => {
    expect(empreinte({ size: 10, mtimeMs: 1000 })).not.toBe(empreinte({ size: 11, mtimeMs: 1000 }));
  });

  it('change quand la date change', () => {
    expect(empreinte({ size: 10, mtimeMs: 1000 })).not.toBe(empreinte({ size: 10, mtimeMs: 2000 }));
  });

  it('est faible (W/) : elle ne prétend pas à l’octet près', () => {
    expect(empreinte({ size: 10, mtimeMs: 1000 })).toMatch(/^W\/"/);
  });

  it('est stable d’un appel à l’autre', () => {
    expect(empreinte({ size: 10, mtimeMs: 1000 })).toBe(empreinte({ size: 10, mtimeMs: 1000 }));
  });
});

describe('servirFichier — requête conditionnelle', () => {
  it('renvoie une ETag, puis 304 SANS corps quand le client la représente', async () => {
    const port = await monter();
    const premiere = await demander(port, '/index.html');
    const etag = String(premiere.entetes.etag);
    expect(etag).toBeTruthy();

    const seconde = await demander(port, '/index.html', { entetes: { 'if-none-match': etag } });
    expect(seconde.statut).toBe(304);
    expect(seconde.brut.length).toBe(0);
    // Le cache doit rester annoncé sur le 304, sinon le client perd la consigne.
    expect(seconde.entetes['cache-control']).toBe('public, max-age=0, must-revalidate');
  });

  it('304 sur une IMAGE : pas de Vary, puisque rien n’est négocié', async () => {
    const port = await monter();
    const premiere = await demander(port, '/image.png');
    const seconde = await demander(port, '/image.png', {
      entetes: { 'if-none-match': String(premiere.entetes.etag) },
    });
    expect(seconde.statut).toBe(304);
    expect(seconde.entetes.vary).toBeUndefined();
  });

  it('une ETag PÉRIMÉE renvoie bien le corps complet', async () => {
    const port = await monter();
    const r = await demander(port, '/index.html', { entetes: { 'if-none-match': 'W/"périmée"' } });
    expect(r.statut).toBe(200);
    expect(r.texte).toContain('Mirabeau');
  });
});

// ---------------------------------------------------------------------------
// Compression
// ---------------------------------------------------------------------------
describe('servirFichier — compression', () => {
  it('compresse un HTML volumineux et le rend lisible à l’identique', async () => {
    const port = await monter();
    const r = await demander(port, '/index.html', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBe('gzip');
    expect(r.texte).toContain('Mirabeau');
    expect(r.brut.length).toBeLessThan(1000);
    // Pas de Content-Length : la taille compressée n'est connue qu'à la fin.
    expect(r.entetes['content-length']).toBeUndefined();
  });

  it('ne compresse PAS une image (déjà compressée)', async () => {
    const port = await monter();
    const r = await demander(port, '/image.png', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(Number(r.entetes['content-length'])).toBe(4096);
  });

  it('ne compresse PAS un fichier plus court que le seuil', async () => {
    const port = await monter();
    const r = await demander(port, '/petit.html', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(r.texte).toBe('<p>ok</p>');
  });

  it('client sans gzip → corps en clair avec sa longueur exacte', async () => {
    const port = await monter();
    const r = await demander(port, '/index.html');
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(Number(r.entetes['content-length'])).toBe(r.brut.length);
  });

  it('pose Vary sur un type compressible, même servi en clair', async () => {
    // Sans ce `Vary`, un cache intermédiaire servirait la version compressée à
    // un client qui ne l'accepte pas.
    const port = await monter();
    const r = await demander(port, '/index.html');
    expect(r.entetes.vary).toBe('Accept-Encoding');
  });

  it('pas de Vary sur une image : rien n’est négocié', async () => {
    const port = await monter();
    const r = await demander(port, '/image.png');
    expect(r.entetes.vary).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Les protections : une lecture en échec ne doit pas arrêter le serveur
// ---------------------------------------------------------------------------
describe('servirFichier — erreurs de flux', () => {
  /**
   * `res` doit être un VRAI flux inscriptible : `servirFichier` y déverse le
   * fichier par `pipe`, qui exige `on`, `write` et `end`. Un objet littéral
   * échouerait sur `dest.on is not a function` — et masquerait ce qu'on veut
   * mesurer. `PassThrough` fournit tout cela, `destroyed` compris.
   */
  function fauxRes() {
    const res = new PassThrough() as PassThrough & {
      writeHead: () => void;
      getHeader: () => undefined;
    };
    res.writeHead = () => {};
    res.getHeader = () => undefined;
    res.resume();                      // on consomme, sinon le flux se bloque
    return res;
  }

  /** Un flux qui échoue dès qu'on le lit — le fichier effacé sous les pieds. */
  function fluxQuiEchoue() {
    const flux = new PassThrough();
    setImmediate(() => flux.emit('error', new Error('disque en défaut')));
    return flux;
  }

  it('une erreur de LECTURE coupe la réponse au lieu d’arrêter le processus', async () => {
    // `pipe` ne propage PAS les erreurs : sans l'écouteur, l'événement `error`
    // reste non capté, et Node arrête le processus — le site tombe entièrement
    // parce qu'un seul fichier n'a pas pu être lu.
    const req = { method: 'GET', headers: {} } as any;
    const res = fauxRes();

    servirFichier(req, res as any, path.join(racine, 'index.html'), {
      creerFlux: fluxQuiEchoue,
    });
    await new Promise((r) => setTimeout(r, 10));

    expect(res.destroyed).toBe(true);
  });

  it('une erreur du COMPRESSEUR coupe aussi la réponse', async () => {
    const req = { method: 'GET', headers: { 'accept-encoding': 'gzip' } } as any;
    const res = fauxRes();
    const gz = new PassThrough();

    servirFichier(req, res as any, path.join(racine, 'index.html'), {
      creerCompresseur: () => gz,
    });
    gz.emit('error', new Error('gzip en défaut'));

    expect(res.destroyed).toBe(true);
  });
});

describe('servirFichier — méthodes et types', () => {
  it('HEAD renvoie les en-têtes sans le corps', async () => {
    const port = await monter();
    const r = await demander(port, '/index.html', { methode: 'HEAD' });
    expect(r.statut).toBe(200);
    expect(r.brut.length).toBe(0);
    expect(r.entetes['content-type']).toBe('text/html; charset=utf-8');
  });

  it('un fichier de _astro/ est annoncé immuable', async () => {
    const port = await monter();
    const r = await demander(port, '/_astro/app.abc123.css');
    expect(r.entetes['cache-control']).toBe('public, max-age=31536000, immutable');
  });

  it('une extension inconnue retombe sur octet-stream', async () => {
    writeFileSync(path.join(racine, 'chose.inconnu'), 'contenu');
    const port = await monter();
    const r = await demander(port, '/chose.inconnu');
    expect(r.entetes['content-type']).toBe('application/octet-stream');
  });

  it.each([...TYPES.entries()] as [string, string][])(
    '%s est annoncé %s',
    async (ext, type) => {
      writeFileSync(path.join(racine, `essai${ext}`), 'x');
      const port = await monter();
      const r = await demander(port, `/essai${ext}`);
      expect(r.entetes['content-type']).toBe(type);
    },
  );
});

/**
 * La fenêtre du REDÉPLOIEMENT.
 *
 * `fichierPour` fait son propre `stat`, puis `servirFichier` en fait un
 * second. Entre les deux, l'hébergeur peut avoir remplacé `dist/`. Un
 * `statSync` nu y levait `ENOENT` — et une exception levée dans l'écouteur de
 * `http.createServer` devient un `uncaughtException` que `server.mjs`
 * n'intercepte pas : le processus s'arrête, donc le site entier tombe.
 *
 * Les protections du module ne couvraient que le FLUX de lecture, jamais le
 * `stat` qui le précède (relevé par la revue de code du 2026-08-18).
 */
describe('servirFichier — le fichier disparaît entre les deux stats', () => {
  function fauxResSimple() {
    const res = new PassThrough() as PassThrough & {
      writeHead: () => void; getHeader: () => undefined;
    };
    res.writeHead = () => {};
    res.getHeader = () => undefined;
    res.resume();
    return res;
  }

  it('ne LÈVE pas — sinon le processus entier s’arrête', () => {
    const res = fauxResSimple();
    expect(() => servirFichier(
      { method: 'GET', headers: {} } as never, res as never,
      path.join(racine, 'disparu-entre-temps.html'),
    )).not.toThrow();
  });

  it('rend `false`, pour que l’appelant retombe sur le gestionnaire', () => {
    const res = fauxResSimple();
    const servi = servirFichier(
      { method: 'GET', headers: {} } as never, res as never,
      path.join(racine, 'disparu-entre-temps.html'),
    );
    expect(servi).toBe(false);
  });

  it('rend `true` quand le fichier est bien là — sans quoi la garde ci-dessus dirait toujours vrai', () => {
    const res = fauxResSimple();
    const servi = servirFichier(
      { method: 'HEAD', headers: {} } as never, res as never,
      path.join(racine, 'index.html'),
    );
    expect(servi).toBe(true);
  });
});
