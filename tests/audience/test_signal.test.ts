/**
 * Tests de `src/lib/audience/signal.mjs` : `POST /api/vue` (AU-1 A, 2026-11-27).
 *
 * La requête et la réponse sont des doublures : on pilote exactement les
 * événements du flux (`data`, `end`, `aborted`, `error`) et on lit ce qui est
 * écrit, sans réseau ni disque, sauf le test « de bout en bout » qui passe par
 * le vrai stockage dans un dossier temporaire.
 */
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { creerSignal } from '../../src/lib/audience/signal.mjs';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { evenementDeSignal } from '../../src/lib/audience/derive.mjs';

import { AUCUN_JOURNAL, ENTETES_OK, envoyer, monter } from './_signal_aide';

describe('evenementDeSignal', () => {
  it('assemble la ligne : nature signal, chemin sans requête, hébergeur, empreinte du jour', () => {
    const ligne = evenementDeSignal({
      chemin: '/a-propos?x=1',
      ip: '203.0.113.9',
      sel: 's',
      maintenant: new Date('2026-11-27T10:20:30Z'),
    });
    expect(Object.keys(ligne).sort()).toEqual([
      'aVuEpisode',
      'aVuFiche',
      'chemin',
      'hebergeur',
      'nature',
      'revenant',
      'ts',
      'visiteur',
    ]);
    // Sans les trois oui/non (ancien script en cache) : « inconnu », jamais « non ».
    expect(ligne).toMatchObject({ revenant: null, aVuEpisode: null, aVuFiche: null });
    expect(ligne).toMatchObject({ ts: '2026-11-27T10:00:00.000Z', nature: 'signal', chemin: '/a-propos', hebergeur: false });
    expect(ligne.visiteur).toMatch(/^[0-9a-f]{12}$/);
  });

  it('sans sel ni adresse : empreinte nulle, jamais d’échec', () => {
    const ligne = evenementDeSignal({ chemin: '/', maintenant: new Date('2026-11-27T10:20:30Z') });
    expect(ligne).toMatchObject({ visiteur: null, hebergeur: false });
  });
});

describe('evenementDeSignal : les trois oui/non (AU-2 B, 2026-11-27)', () => {
  it('écrit exactement les trois oui/non reçus, rien d’autre', () => {
    const ligne = evenementDeSignal({
      chemin: '/',
      ip: '203.0.113.9',
      sel: 's',
      maintenant: new Date('2026-11-27T10:20:30Z'),
      revenant: true,
      aVuEpisode: false,
      aVuFiche: true,
    });
    expect(ligne).toEqual({
      ts: '2026-11-27T10:00:00.000Z',
      nature: 'signal',
      chemin: '/',
      hebergeur: false,
      visiteur: ligne.visiteur,
      revenant: true,
      aVuEpisode: false,
      aVuFiche: true,
    });
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

describe('POST /api/vue : les trois oui/non (AU-2 B, 2026-11-27)', () => {
  const trois = { revenant: true, aVuEpisode: false, aVuFiche: true };
  const corps = (o: Record<string, unknown>) => JSON.stringify({ chemin: '/a-propos', ...o });

  it('les écrit sur la ligne, telles quelles', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { corps: corps(trois) });
    expect(f.statut()).toBe(204);
    expect(ecrit[0].ligne).toMatchObject(trois);
  });

  it('un ancien script en cache, qui n’envoie que le chemin, reste accepté (champs nuls)', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler);
    expect(f.statut()).toBe(204);
    expect(ecrit[0].ligne).toMatchObject({ revenant: null, aVuEpisode: null, aVuFiche: null });
  });

  it('un champ inconnu est ignoré : il n’entre jamais sur la ligne', async () => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { corps: corps({ ...trois, identifiant: 'abc', ne: '2026-01-01' }) });
    expect(f.statut()).toBe(204);
    expect(Object.keys(ecrit[0].ligne).sort()).toEqual([
      'aVuEpisode',
      'aVuFiche',
      'chemin',
      'hebergeur',
      'nature',
      'revenant',
      'ts',
      'visiteur',
    ]);
  });

  it.each([
    ['texte', { ...trois, revenant: 'true' }],
    ['nombre', { ...trois, aVuEpisode: 1 }],
    ['nul', { ...trois, aVuFiche: null }],
    ['objet', { ...trois, revenant: {} }],
    ['tableau', { ...trois, revenant: [true] }],
    ['un seul champ présent', { revenant: true }],
    ['deux champs présents sur trois', { revenant: true, aVuEpisode: true }],
  ])('%s : 400, rien d’écrit', async (_nom, o) => {
    const { signaler, ecrit } = monter();
    const f = await envoyer(signaler, { corps: corps(o) });
    expect(f.statut()).toBe(400);
    expect(ecrit).toHaveLength(0);
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
