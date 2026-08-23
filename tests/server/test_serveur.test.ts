/**
 * Tests de `src/server/serveur.mjs` — l'aiguillage statique / Astro.
 *
 * Le gestionnaire Astro est remplacé par un faux qui écrit selon la MÊME
 * convention (`writeHead(statut, objetEnTêtes)`), et qui enregistre s'il a été
 * appelé. C'est ce qui permet de vérifier l'aiguillage sans build : la
 * question posée ici n'est pas « que rend Astro ? » mais « qui répond ? ».
 */
import { afterEach, beforeAll, afterAll, describe, expect, it, vi } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { creerServeur, fermerProprement, repondre404, traiter } from '../../src/server/serveur.mjs';
import { demander, demarrer } from './_client';

const LONG = 'Il pleure dans mon cœur comme il pleut sur la ville. '.repeat(60);

let racine: string;
let arreterCourant: (() => Promise<void>) | null = null;

beforeAll(() => {
  racine = mkdtempSync(path.join(tmpdir(), 'reco-aiguillage-'));
  writeFileSync(path.join(racine, 'index.html'), `<!doctype html><p>${LONG}</p>`);
});

afterAll(() => rmSync(racine, { recursive: true, force: true }));

afterEach(async () => {
  if (arreterCourant) await arreterCourant();
  arreterCourant = null;
});

type Appels = { recu: string[] };

/** Faux gestionnaire Astro : répond, ou passe la main via `suivant()`. */
function fauxHandler(appels: Appels, reponse: string | null) {
  return (req: any, res: any, suivant: () => void) => {
    appels.recu.push(`${req.method} ${req.url}`);
    if (reponse === null) return suivant();
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Length': Buffer.byteLength(reponse),
    });
    res.end(reponse);
  };
}

async function monter(reponse: string | null): Promise<{ port: number; appels: Appels }> {
  const appels: Appels = { recu: [] };
  const serveur = creerServeur(fauxHandler(appels, reponse), racine);
  const { port, arreter } = await demarrer(serveur);
  arreterCourant = arreter;
  return { port, appels };
}

describe('traiter — qui répond ?', () => {
  it('un fichier construit est servi SANS déranger le gestionnaire', async () => {
    const { port, appels } = await monter('page à la demande');
    const r = await demander(port, '/index.html');
    expect(r.texte).toContain('pleure');
    expect(appels.recu).toEqual([]);
  });

  it('une URL sans fichier va au gestionnaire', async () => {
    const { port, appels } = await monter('page à la demande');
    const r = await demander(port, '/api/quelque-chose');
    expect(r.texte).toBe('page à la demande');
    expect(appels.recu).toEqual(['GET /api/quelque-chose']);
  });

  it('un POST vers un fichier existant va au GESTIONNAIRE, pas au disque', async () => {
    // Servir la page avec un 200 laisserait croire que l'envoi a été pris en
    // compte, alors que rien n'a été traité.
    const { port, appels } = await monter('traité');
    const r = await demander(port, '/index.html', { methode: 'POST' });
    expect(appels.recu).toEqual(['POST /index.html']);
    expect(r.texte).toBe('traité');
  });

  it('HEAD sur un fichier reste servi depuis le disque', async () => {
    const { port, appels } = await monter('inutile');
    const r = await demander(port, '/index.html', { methode: 'HEAD' });
    expect(r.statut).toBe(200);
    expect(appels.recu).toEqual([]);
  });

  it('le gestionnaire qui passe la main → 404 avec un corps lisible', async () => {
    const { port } = await monter(null);
    const r = await demander(port, '/nulle-part');
    expect(r.statut).toBe(404);
    expect(r.texte).toBe('Page introuvable');
  });

  it('le 404 n’est PAS compressé : il est trop court pour que ce soit utile', async () => {
    const { port } = await monter(null);
    const r = await demander(port, '/nulle-part', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBeUndefined();
    expect(Number(r.entetes['content-length'])).toBe(Buffer.byteLength('Page introuvable'));
  });

  it('la réponse du gestionnaire est COMPRESSÉE quand elle s’y prête', async () => {
    // C'est la raison d'être de tout ce montage : sans l'enveloppe, les routes
    // à la demande partiraient en clair.
    const { port } = await monter(LONG);
    const r = await demander(port, '/route/a/la/demande', { entetes: { 'accept-encoding': 'gzip' } });
    expect(r.entetes['content-encoding']).toBe('gzip');
    expect(r.texte).toBe(LONG);
  });

  it('une tentative de traversée ne fuit pas vers le disque', async () => {
    const { port, appels } = await monter('rendu par Astro');
    const r = await demander(port, '/../../../etc/passwd');
    // Le chemin est refusé par la résolution : la requête finit au
    // gestionnaire, qui répond normalement — jamais le contenu du disque.
    expect(r.texte).toBe('rendu par Astro');
    expect(appels.recu).toHaveLength(1);
  });

  it('une URL absente est tolérée (req.url vaut undefined)', () => {
    // Node garantit `req.url`, mais le type le déclare optionnel et le repli
    // `|| '/'` existe pour cela : on vérifie qu'il ne lève pas.
    //
    // La racine employée ici est VIDE, sinon `/` trouverait `index.html` et le
    // test mesurerait le service d'un fichier au lieu du repli — c'est
    // l'erreur qu'a d'abord commise ce test.
    const vide = mkdtempSync(path.join(tmpdir(), 'reco-vide-'));
    const appels: Appels = { recu: [] };
    const req = { method: 'GET', headers: {} } as any;
    const res = { writeHead: vi.fn(), end: vi.fn(), getHeader: () => undefined } as any;

    traiter(fauxHandler(appels, null), vide, req, res);

    expect(appels.recu).toEqual(['GET undefined']);
    expect(res.writeHead).toHaveBeenCalledWith(404, expect.any(Object));
    rmSync(vide, { recursive: true, force: true });
  });
});

describe('fermerProprement', () => {
  it('ferme le serveur et sort avec 0 sur le signal', async () => {
    const ferme = vi.fn((rappel: () => void) => rappel());
    const sortie = vi.fn();
    const faux = { close: ferme } as any;

    fermerProprement(faux, { signaux: ['SIGUSR2'], sortie });
    process.emit('SIGUSR2' as never);
    // `once` est synchrone ici : le rappel de `close` est appelé aussitôt.
    expect(ferme).toHaveBeenCalledTimes(1);
    expect(sortie).toHaveBeenCalledWith(0);
    process.removeAllListeners('SIGUSR2');
  });

  it('écoute SIGTERM et SIGINT par défaut', () => {
    // SIGTERM est ce que l'hébergeur envoie à chaque redéploiement : c'est le
    // signal qui compte réellement en production.
    const avantTerm = process.listenerCount('SIGTERM');
    const avantInt = process.listenerCount('SIGINT');
    const faux = { close: vi.fn() } as any;

    fermerProprement(faux, { sortie: vi.fn() });

    expect(process.listenerCount('SIGTERM')).toBe(avantTerm + 1);
    expect(process.listenerCount('SIGINT')).toBe(avantInt + 1);
    process.removeAllListeners('SIGTERM');
    process.removeAllListeners('SIGINT');
  });

  it('renvoie le serveur, pour permettre le chaînage', () => {
    const faux = { close: vi.fn() } as any;
    expect(fermerProprement(faux, { signaux: ['SIGUSR2'], sortie: vi.fn() })).toBe(faux);
    process.removeAllListeners('SIGUSR2');
  });
});

describe('la page 404 construite', () => {
  // Racine SEPAREE : les tests ci-dessus verifient le repli du repli — le
  // texte brut quand `404.html` n'a pas ete construite. Poser le fichier dans
  // leur racine leur ferait perdre leur objet.
  let racine404: string;

  beforeAll(() => {
    racine404 = mkdtempSync(path.join(tmpdir(), 'reco-404-'));
    writeFileSync(
      path.join(racine404, '404.html'),
      '<!doctype html><title>Page introuvable</title><a href="/recherche">Rechercher</a>',
    );
  });

  afterAll(() => rmSync(racine404, { recursive: true, force: true }));

  async function monter404() {
    const serveur = creerServeur(fauxHandler({ recu: [] }, null), racine404);
    const { port, arreter } = await demarrer(serveur);
    arreterCourant = arreter;
    return port;
  }

  it('sert la page construite plutot que le texte brut', async () => {
    // Seize octets de `text/plain` laissaient le visiteur sans navigation.
    const port = await monter404();
    const r = await demander(port, '/nulle-part');

    expect(r.statut).toBe(404);
    expect(r.entetes['content-type']).toContain('text/html');
    expect(r.texte).toContain('Rechercher');
  });

  it('garde le statut 404, pas 200', async () => {
    // Une page d'erreur servie en 200 fait indexer le vide.
    const port = await monter404();

    expect((await demander(port, '/nulle-part')).statut).toBe(404);
  });

  it('annonce une longueur exacte', async () => {
    const port = await monter404();
    const r = await demander(port, '/nulle-part');

    expect(Number(r.entetes['content-length'])).toBe(r.brut.length);
  });

  it('retombe sur le texte brut si la lecture echoue', async () => {
    // Une erreur de lecture ne doit pas remonter : elle arreterait le
    // processus, donc tout le site, pour une page manquante.
    const res = {
      writeHead: vi.fn(),
      end: vi.fn(),
    };
    repondre404(res as never, '/peu-importe', {
      lire: () => { throw new Error('disque en vrac'); },
    });

    expect(res.writeHead).toHaveBeenCalledWith(404, expect.objectContaining({
      'Content-Type': 'text/plain; charset=utf-8',
    }));
    expect(res.end).toHaveBeenCalledWith('Page introuvable');
  });
});
