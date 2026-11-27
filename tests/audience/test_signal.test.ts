/**
 * Tests de `src/lib/audience/signal.mjs` : `POST /api/vue` (AU-1 A, 2026-11-27).
 *
 * La requête et la réponse sont des doublures : on pilote exactement les
 * événements du flux (`data`, `end`, `aborted`, `error`) et on lit ce qui est
 * écrit, sans réseau ni disque, sauf le test « de bout en bout » qui passe par
 * le vrai stockage dans un dossier temporaire.
 */
import { EventEmitter } from 'node:events';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { creerSignal } from '../../src/lib/audience/signal.mjs';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { evenementDeSignal } from '../../src/lib/audience/derive.mjs';

const ENTETES_OK = { host: 'unebonnere.co', origin: 'https://unebonnere.co' };

type Fausse = {
  req: any;
  res: any;
  /** La réponse est partie (ou ne partira jamais, pour un client coupé). */
  statut: () => number | undefined;
};

function fabriquer(
  { corps = '{"chemin":"/a-propos"}', entetes = ENTETES_OK, methode = 'POST', flux = true } = {} as any,
): Fausse {
  const req: any = new EventEmitter();
  req.method = methode;
  req.url = '/api/vue';
  req.headers = { ...entetes };
  req.socket = { remoteAddress: '203.0.113.9' };
  const res: any = {
    code: undefined as number | undefined,
    entetes: {} as Record<string, string>,
    headersSent: false,
    writeHead(c: number, e: Record<string, string> = {}) {
      this.code = c;
      this.entetes = e;
      this.headersSent = true;
    },
    end: vi.fn(),
  };
  if (flux) {
    // Le corps arrive après que le gestionnaire s'est abonné au flux.
    queueMicrotask(() => {
      if (corps) req.emit('data', Buffer.from(corps));
      req.emit('end');
    });
  }
  return { req, res, statut: () => res.code };
}

const AUCUN_JOURNAL = () => ({ warn: vi.fn(), error: vi.fn() });

function monter(extra: Record<string, unknown> = {}) {
  const ecrit: any[] = [];
  const ecrire = vi.fn((ligne: any, source: string) => {
    ecrit.push({ ligne, source });
    return true;
  });
  const journal = AUCUN_JOURNAL();
  const signaler = creerSignal({
    ecrire,
    journal,
    sel: 'sel-de-test',
    horloge: () => Date.parse('2026-11-27T10:20:30Z'),
    ...extra,
  });
  return { signaler, ecrit, ecrire, journal };
}

async function envoyer(signaler: any, options: any = {}) {
  const f = fabriquer(options);
  await signaler(f.req, f.res);
  return f;
}

describe('evenementDeSignal', () => {
  it('assemble la ligne : nature signal, chemin sans requête, hébergeur, empreinte du jour', () => {
    const ligne = evenementDeSignal({
      chemin: '/a-propos?x=1',
      ip: '203.0.113.9',
      sel: 's',
      maintenant: new Date('2026-11-27T10:20:30Z'),
    });
    expect(Object.keys(ligne).sort()).toEqual(['chemin', 'hebergeur', 'nature', 'ts', 'visiteur']);
    expect(ligne).toMatchObject({ ts: '2026-11-27T10:00:00.000Z', nature: 'signal', chemin: '/a-propos', hebergeur: false });
    expect(ligne.visiteur).toMatch(/^[0-9a-f]{12}$/);
  });

  it('sans sel ni adresse : empreinte nulle, jamais d’échec', () => {
    const ligne = evenementDeSignal({ chemin: '/', maintenant: new Date('2026-11-27T10:20:30Z') });
    expect(ligne).toMatchObject({ visiteur: null, hebergeur: false });
  });
});

describe('POST /api/vue : acceptation', () => {
  it('écrit une ligne nature signal et répond 204 sans corps', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler);
    expect(f.statut()).toBe(204);
    expect(ecrit).toHaveLength(1);
    expect(ecrit[0].ligne).toMatchObject({ nature: 'signal', chemin: '/a-propos' });
    expect(ecrit[0].source).toBe('_site');
  });

  it('range le signal sous la source du chemin, comme une visite', async () => {
    const { signaler, ecrit } = monter({ sourcesConnues: new Set(['un-bon-moment']) });
    await envoyer(signaler, { corps: '{"chemin":"/un-bon-moment/s6/e11"}' });
    expect(ecrit[0].source).toBe('un-bon-moment');
  });

  it('accepte un corps text/plain (sendBeacon) comme du JSON', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, {
      entetes: { ...ENTETES_OK, 'content-type': 'text/plain;charset=UTF-8' },
    });
    expect(f.statut()).toBe(204);
    expect(ecrit).toHaveLength(1);
  });

  it('accepte un signal sous Sec-GPC et DNT : il ne porte aucun identifiant', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { entetes: { ...ENTETES_OK, 'sec-gpc': '1', dnt: '1' } });
    expect(f.statut()).toBe(204);
    expect(ecrit).toHaveLength(1);
  });

  it('porte la même empreinte du jour que celle d’une visite (dernier saut de x-forwarded-for)', async () => {
    const { signaler, ecrit } = monter();
    await envoyer(signaler, {
      entetes: { ...ENTETES_OK, 'x-forwarded-for': '1.2.3.4, 203.0.113.50' },
    });
    const attendu = evenementDeSignal({
      chemin: '/a-propos',
      ip: '203.0.113.50',
      sel: 'sel-de-test',
      maintenant: new Date('2026-11-27T10:20:30Z'),
    });
    expect(ecrit[0].ligne.visiteur).toBe(attendu.visiteur);
  });

  it('sans sel : la ligne s’écrit avec un visiteur nul', async () => {
    const { signaler, ecrit } = monter({ sel: null });
    const avant = process.env.RECO_AUDIENCE_SALT;
    delete process.env.RECO_AUDIENCE_SALT;
    try {
      const f = await envoyer(signaler);
      expect(f.statut()).toBe(204);
      expect(ecrit[0].ligne.visiteur).toBeNull();
    } finally {
      if (avant !== undefined) process.env.RECO_AUDIENCE_SALT = avant;
    }
  });

  it('prend le sel dans RECO_AUDIENCE_SALT quand aucune option ne le donne', async () => {
    const { signaler, ecrit } = monter({ sel: undefined });
    const avant = process.env.RECO_AUDIENCE_SALT;
    process.env.RECO_AUDIENCE_SALT = 'sel-env';
    try {
      await envoyer(signaler);
      expect(ecrit[0].ligne.visiteur).toMatch(/^[0-9a-f]{12}$/);
    } finally {
      if (avant === undefined) delete process.env.RECO_AUDIENCE_SALT;
      else process.env.RECO_AUDIENCE_SALT = avant;
    }
  });

  it('de bout en bout : la ligne arrive dans le JSONL du jour, avec le vrai stockage', async () => {
    const cwd = mkdtempSync(path.join(tmpdir(), 'reco-signal-'));
    try {
      const signaler = creerSignal({
        cwd,
        sel: 's',
        horloge: () => Date.parse('2026-11-27T10:20:30Z'),
        journal: AUCUN_JOURNAL(),
      });
      const f = await envoyer(signaler);
      expect(f.statut()).toBe(204);
      const fichier = path.join(cwd, 'tools', 'output', 'audience', '_site', '2026-11-27.jsonl');
      const ligne = JSON.parse(readFileSync(fichier, 'utf8').trim());
      expect(ligne).toMatchObject({ nature: 'signal', chemin: '/a-propos', hebergeur: false });
    } finally {
      rmSync(cwd, { recursive: true, force: true });
    }
  });
});

describe('POST /api/vue : refus', () => {
  it.each(['GET', 'PUT', 'HEAD'])('%s : 405 avec Allow: POST', async (methode) => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { methode, flux: false });
    expect(f.statut()).toBe(405);
    expect(f.res.entetes.Allow).toBe('POST');
    expect(ecrit).toHaveLength(0);
  });

  it.each([
    ['JSON invalide', '{pas du json'],
    ['pas un objet', '[1]'],
    ['sans chemin', '{}'],
    ['chemin non texte', '{"chemin":12}'],
    ['chemin relatif', '{"chemin":"a-propos"}'],
    ['chemin trop long', JSON.stringify({ chemin: '/' + 'a'.repeat(600) })],
    ['null', 'null'],
    ['corps vide', ''],
  ])('%s : 400', async (_nom, corps) => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { corps });
    expect(f.statut()).toBe(400);
    expect(ecrit).toHaveLength(0);
  });

  it.each([
    '/audience',
    '/audience/',
    '/api/click',
    '/_astro/x.js',
    '/style.css',
    '/meta',
    '/meta/podcast/x',
    '/meta?x=1',
  ])('chemin exclu de la mesure (%s) : 400', async (chemin) => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { corps: JSON.stringify({ chemin }) });
    expect(f.statut()).toBe(400);
    expect(ecrit).toHaveLength(0);
  });

  it('une page dont le nom commence par meta reste une page', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { corps: '{"chemin":"/metaphore"}' });
    expect(f.statut()).toBe(204);
    expect(ecrit).toHaveLength(1);
  });
});

describe('POST /api/vue : origine (R-3)', () => {
  it.each([
    ['sans Origin', { host: 'unebonnere.co' }],
    ['sans Host', { origin: 'https://unebonnere.co' }],
    ['autre site', { host: 'unebonnere.co', origin: 'https://exemple.org' }],
    ['Origin illisible', { host: 'unebonnere.co', origin: 'null' }],
    ['Host illisible', { host: 'a b', origin: 'https://unebonnere.co' }],
    ['même hôte mais Sec-Fetch-Site cross-site', { ...ENTETES_OK, 'sec-fetch-site': 'cross-site' }],
    ['même hôte mais Sec-Fetch-Site same-site', { ...ENTETES_OK, 'sec-fetch-site': 'same-site' }],
  ])('%s : 403', async (_nom, entetes) => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { entetes, flux: false });
    expect(f.statut()).toBe(403);
    expect(ecrit).toHaveLength(0);
  });

  it('derrière le mandataire, en http et sans SITE_URL : même nom d’hôte = accepté', async () => {
    const avant = process.env.SITE_URL;
    delete process.env.SITE_URL;
    try {
      const { signaler, ecrit } = monter();
      const f = await envoyer(signaler, {
        entetes: {
          host: 'unebonnere.co',
          origin: 'https://unebonnere.co',
          'x-forwarded-proto': 'http',
          'sec-fetch-site': 'same-origin',
        },
      });
      expect(f.statut()).toBe(204);
      expect(ecrit).toHaveLength(1);
    } finally {
      if (avant !== undefined) process.env.SITE_URL = avant;
    }
  });

  it('le port et la casse ne comptent pas, seul le nom d’hôte', async () => {
    const { signaler } = monter();
    const f = await envoyer(signaler, {
      entetes: { host: '127.0.0.1:4402', origin: 'http://127.0.0.1:4402' },
    });
    expect(f.statut()).toBe(204);
    const g = await envoyer(signaler, {
      entetes: { host: 'UneBonneRe.co', origin: 'https://unebonnere.co' },
    });
    expect(g.statut()).toBe(204);
  });
});

describe('POST /api/vue : limites d’abus (R-4)', () => {
  it('un Content-Length annoncé au-delà de 1 Kio : 413 sans rien lire', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, {
      entetes: { ...ENTETES_OK, 'content-length': '5000' },
      flux: false,
    });
    expect(f.statut()).toBe(413);
    expect(f.res.entetes.Connection).toBe('close');
    expect(ecrit).toHaveLength(0);
  });

  it('un corps qui dépasse 1 Kio en route : 413, coupé sans attendre la fin', async () => {
    const { signaler, ecrit } = monter();
    const f = fabriquer({ flux: false });
    const fin = signaler(f.req, f.res);
    await Promise.resolve();
    f.req.emit('data', Buffer.alloc(600));
    f.req.emit('data', Buffer.alloc(600));
    await fin;
    expect(f.statut()).toBe(413);
    expect(f.req.listenerCount('data')).toBe(0);
    expect(ecrit).toHaveLength(0);
  });

  it('un corps de 1 Kio pile passe la limite (puis échoue sur le JSON, pas sur la taille)', async () => {
    const { signaler } = monter();
    const f = await envoyer(signaler, { corps: 'x'.repeat(1024) });
    expect(f.statut()).toBe(400);
  });

  it('un corps qui n’arrive pas en 5 s : 408', async () => {
    const { signaler, ecrit } = monter({ delaiMs: 15 });
    const f = await envoyer(signaler, { flux: false });
    expect(f.statut()).toBe(408);
    expect(f.req.listenerCount('data')).toBe(0);
    expect(ecrit).toHaveLength(0);
  });

  it('une erreur de flux ou un client parti : rien écrit, aucune réponse, aucune exception', async () => {
    for (const evenement of ['error', 'aborted']) {
      const { signaler, ecrit } = monter();
      const f = fabriquer({ flux: false });
      const fin = signaler(f.req, f.res);
      await Promise.resolve();
      f.req.emit(evenement, new Error('coupé'));
      await fin;
      expect(f.statut()).toBeUndefined();
      expect(ecrit).toHaveLength(0);
      // Un `error` tardif, après la fin, ne doit pas lever.
      expect(() => f.req.emit('error', new Error('tard'))).not.toThrow();
    }
  });

  it('au 31e signal de la minute pour une même empreinte : 429 ; la minute suivante repart', async () => {
    let t = Date.parse('2026-11-27T10:20:00Z');
    const { signaler, ecrit } = monter({ horloge: () => t });
    for (let i = 0; i < 30; i++) expect((await envoyer(signaler)).statut()).toBe(204);
    expect((await envoyer(signaler)).statut()).toBe(429);
    expect(ecrit).toHaveLength(30);
    t += 60_000;
    expect((await envoyer(signaler)).statut()).toBe(204);
  });

  it('la limite est par empreinte : un autre visiteur n’est pas touché', async () => {
    const { signaler } = monter();
    for (let i = 0; i < 31; i++) await envoyer(signaler);
    const autre = await envoyer(signaler, {
      entetes: { ...ENTETES_OK, 'x-forwarded-for': '198.51.100.7' },
    });
    expect(autre.statut()).toBe(204);
  });

  it('sans sel, la limite se fait sur l’adresse, qui n’est jamais écrite', async () => {
    const { signaler } = monter({ sel: null, parMinute: 1 });
    const avant = process.env.RECO_AUDIENCE_SALT;
    delete process.env.RECO_AUDIENCE_SALT;
    try {
      expect((await envoyer(signaler)).statut()).toBe(204);
      expect((await envoyer(signaler)).statut()).toBe(429);
    } finally {
      if (avant !== undefined) process.env.RECO_AUDIENCE_SALT = avant;
    }
  });

  it('sans sel ni adresse, tous partagent une même clé : la limite tient quand même', async () => {
    const { signaler } = monter({ sel: null, parMinute: 1 });
    const avant = process.env.RECO_AUDIENCE_SALT;
    delete process.env.RECO_AUDIENCE_SALT;
    try {
      const f1 = fabriquer();
      f1.req.socket = {};
      await signaler(f1.req, f1.res);
      const f2 = fabriquer();
      f2.req.socket = {};
      await signaler(f2.req, f2.res);
      expect([f1.statut(), f2.statut()]).toEqual([204, 429]);
    } finally {
      if (avant !== undefined) process.env.RECO_AUDIENCE_SALT = avant;
    }
  });

  it('la table de limitation est bornée : la plus ancienne entrée tombe', async () => {
    const { signaler } = monter({ maxEmpreintes: 2, parMinute: 1 });
    const depuis = (ip: string) => ({ ...ENTETES_OK, 'x-forwarded-for': ip });
    await envoyer(signaler, { entetes: depuis('10.0.0.1') });
    await envoyer(signaler, { entetes: depuis('10.0.0.2') });
    await envoyer(signaler, { entetes: depuis('10.0.0.3') }); // 10.0.0.1 tombe
    // 10.0.0.1 a été oubliée : elle repart de zéro, au lieu d'un 429.
    expect((await envoyer(signaler, { entetes: depuis('10.0.0.1') })).statut()).toBe(204);
    // 10.0.0.3 est encore là, et son quota est épuisé.
    expect((await envoyer(signaler, { entetes: depuis('10.0.0.3') })).statut()).toBe(429);
  });

  it('plafond de lignes du jour : au-delà, 204 sans écrire, journalisé une seule fois', async () => {
    const { signaler, ecrit, journal } = monter({ maxLignesJour: 2, parMinute: 100 });
    for (let i = 0; i < 5; i++) expect((await envoyer(signaler)).statut()).toBe(204);
    expect(ecrit).toHaveLength(2);
    expect(journal.warn).toHaveBeenCalledTimes(1);
    expect(journal.warn.mock.calls[0][0]).toContain('plafond');
  });

  it('plafond de lignes du jour : sans méthode warn, aucune exception', async () => {
    const { signaler } = monter({ maxLignesJour: 0, journal: {} });
    expect((await envoyer(signaler)).statut()).toBe(204);
  });
});

describe('POST /api/vue : écriture et minuit (R-13)', () => {
  it('écriture refusée (false) : journalisée une seule fois, et 204 quand même', async () => {
    const { signaler, journal } = monter({ ecrire: () => false, parMinute: 100 });
    expect((await envoyer(signaler)).statut()).toBe(204);
    expect((await envoyer(signaler)).statut()).toBe(204);
    expect(journal.warn).toHaveBeenCalledTimes(1);
  });

  it('écriture qui lève : journalisée, et 204 quand même', async () => {
    const { signaler, journal } = monter({
      ecrire: () => {
        throw new Error('disque plein');
      },
    });
    expect((await envoyer(signaler)).statut()).toBe(204);
    expect(journal.warn.mock.calls[0].join(' ')).toContain('disque plein');
  });

  it('écriture qui lève sans message : journalisée avec la valeur brute', async () => {
    const { signaler, journal } = monter({
      ecrire: () => {
        throw 'boum';
      },
    });
    expect((await envoyer(signaler)).statut()).toBe(204);
    expect(journal.warn.mock.calls[0].join(' ')).toContain('boum');
  });

  it('erreur inattendue : journalisée, 500', async () => {
    const { signaler, journal } = monter({
      horloge: () => {
        throw new Error('horloge cassée');
      },
    });
    const f = await envoyer(signaler);
    expect(f.statut()).toBe(500);
    expect(journal.error).toHaveBeenCalledTimes(1);
  });

  it('erreur inattendue après l’envoi de la réponse : journalisée, pas de seconde réponse', async () => {
    const erreur = vi.fn();
    const { signaler } = monter({ journal: { warn: () => {}, error: erreur } });
    const f = fabriquer();
    const codes: number[] = [];
    const ecrireEntete = f.res.writeHead.bind(f.res);
    f.res.writeHead = (c: number, e: any) => {
      codes.push(c);
      ecrireEntete(c, e);
    };
    f.res.end = () => {
      throw new Error('socket fermée');
    };
    await signaler(f.req, f.res);
    expect(codes).toEqual([204]);
    expect(erreur).toHaveBeenCalledTimes(1);
  });

  it('erreur inattendue qui n’est pas une Error : journalisée telle quelle', async () => {
    const { signaler, journal } = monter({
      horloge: () => {
        throw 'texte brut';
      },
    });
    expect((await envoyer(signaler)).statut()).toBe(500);
    expect(journal.error.mock.calls[0].join(' ')).toContain('texte brut');
  });

  it('erreur inattendue sans méthode error sur le journal : aucune exception', async () => {
    const { signaler } = monter({
      journal: {},
      horloge: () => {
        throw new Error('x');
      },
    });
    expect((await envoyer(signaler)).statut()).toBe(500);
  });

  it('une requête sans en-têtes : refusée proprement (403)', async () => {
    const { signaler } = monter();
    const f = fabriquer({ flux: false });
    delete f.req.headers;
    await signaler(f.req, f.res);
    expect(f.statut()).toBe(403);
  });

  it('minuit UTC : le fichier du jour, l’empreinte et le plafond changent ensemble', async () => {
    let t = Date.parse('2026-11-27T23:59:59.900Z');
    const { signaler, ecrit, journal } = monter({ horloge: () => t, maxLignesJour: 1 });
    await envoyer(signaler); // écrit, plafond du 27 atteint
    await envoyer(signaler); // refusé : plafond journalisé
    t = Date.parse('2026-11-28T00:00:00.100Z');
    await envoyer(signaler); // nouveau jour : compteur remis à zéro
    expect(ecrit).toHaveLength(2);
    const [avant, apres] = ecrit.map((e) => e.ligne);
    expect(avant.ts.slice(0, 10)).toBe('2026-11-27');
    expect(apres.ts.slice(0, 10)).toBe('2026-11-28');
    expect(apres.visiteur).not.toBe(avant.visiteur);
    expect(journal.warn).toHaveBeenCalledTimes(1);
  });
});

describe('adresse exclue (R-14, 27/11/2026)', () => {
  it('répond 204 sans rien écrire ni compter', async () => {
    const { signaler, ecrit } = monter({ exclut: (ip: string) => ip === '203.0.113.9' });
    const f = await envoyer(signaler);
    expect(f.statut()).toBe(204);
    expect(ecrit).toHaveLength(0);
  });

  it('une autre adresse est comptée', async () => {
    const { signaler, ecrit } = monter({ exclut: () => false });
    await envoyer(signaler);
    expect(ecrit).toHaveLength(1);
  });

  it('une adresse exclue passe quand même après les contrôles d’origine : sans Origin, 403', async () => {
    const { signaler } = monter({ exclut: () => true });
    const f = await envoyer(signaler, { entetes: {} });
    expect(f.statut()).toBe(403);
  });
});
