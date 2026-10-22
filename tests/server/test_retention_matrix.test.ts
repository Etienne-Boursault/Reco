/**
 * Tests de `src/server/retention-matrix.mjs` : les notifications de
 * signalement de plus de 12 mois sont effacées du salon Matrix. Faux serveur
 * Matrix en mémoire : aucun appel réseau.
 */
import { describe, expect, it } from 'vitest';

import {
  estNotificationAEffacer, purgerNotificationsMatrix,
} from '../../src/server/retention-matrix.mjs';

const MAINTENANT = new Date('2026-10-22T12:00:00Z');
const ENV = { RECO_MATRIX_HOMESERVER: 'https://matrix.test/', RECO_MATRIX_TOKEN: 'jeton', RECO_MATRIX_ROOM: '!salon:test' };
const VIEUX = Date.parse('2025-06-01T00:00:00Z');
const RECENT = Date.parse('2026-09-01T00:00:00Z');

const signalement = (id: string, ts: number, par = true) => ({
  event_id: id, origin_server_ts: ts,
  content: { body: `🚩 Nouveau signalement — Erreur\nDétails : x${par ? '\nPar : Ana · ana@test.fr' : ''}\nRéf : r · s` },
});
const autre = (id: string, ts: number) => ({ event_id: id, origin_server_ts: ts, content: { body: '✅ épisode publié' } });

/** Faux serveur : pages successives de `/messages`, rédactions enregistrées. */
function serveur(pages: Array<{ chunk?: unknown[]; end?: string }>, echec: { whoami?: boolean; redact?: boolean } = {}) {
  const appels: string[] = [];
  const rediges: string[] = [];
  let page = 0;
  const fetchImpl = async (url: string, init: { method?: string; headers?: Record<string, string>; body?: string } = {}) => {
    appels.push(url);
    expect(init.headers?.Authorization).toBe('Bearer jeton');
    const reponse = (status: number, corps: unknown) => ({ ok: status < 400, status, json: async () => corps });
    if (url.endsWith('/account/whoami')) return echec.whoami ? reponse(401, {}) : reponse(200, { user_id: '@bot:test' });
    if (url.includes('/redact/')) {
      if (echec.redact) return reponse(403, {});
      rediges.push(decodeURIComponent(url.split('/redact/')[1].split('/')[0]));
      expect(JSON.parse(init.body ?? '{}').reason).toContain('12 mois');
      return reponse(200, { event_id: '$r' });
    }
    const params = new URL(url).searchParams;
    expect(params.get('dir')).toBe('f');
    expect(JSON.parse(params.get('filter') ?? '{}').senders).toEqual(['@bot:test']);
    if (page > 0) expect(params.get('from')).toBe(pages[page - 1].end);
    return reponse(200, pages[Math.min(page++, pages.length - 1)]);
  };
  return { fetchImpl, appels, rediges };
}

describe('estNotificationAEffacer', () => {
  it("ne vise que les signalements qui portent encore des coordonnées", () => {
    expect(estNotificationAEffacer(signalement('a', 0).content)).toBe(true);
    expect(estNotificationAEffacer(signalement('a', 0, false).content)).toBe(false);
    expect(estNotificationAEffacer(autre('b', 0).content)).toBe(false);
    expect(estNotificationAEffacer({})).toBe(false); // message déjà rédigé
    expect(estNotificationAEffacer(undefined)).toBe(false);
  });
});

describe('purgerNotificationsMatrix', () => {
  it('ne fait rien sans configuration Matrix', async () => {
    const { fetchImpl, appels } = serveur([]);
    expect(await purgerNotificationsMatrix({ env: {}, fetchImpl, maintenant: MAINTENANT })).toBe(0);
    expect(appels).toEqual([]);
  });

  it("efface les vieilles notifications et s'arrête au premier message récent", async () => {
    const { fetchImpl, rediges, appels } = serveur([
      { chunk: [signalement('$a', VIEUX), autre('$b', VIEUX), signalement('$c', VIEUX, false)], end: 't1' },
      { chunk: [signalement('$d', VIEUX), signalement('$e', RECENT)], end: 't2' },
      { chunk: [signalement('$jamais', VIEUX)], end: 't3' },
    ]);
    const effaces = await purgerNotificationsMatrix({ env: ENV, fetchImpl, maintenant: MAINTENANT });
    expect(effaces).toBe(2);
    expect(rediges).toEqual(['$a', '$d']);
    expect(appels[1]).toContain('https://matrix.test/_matrix/client/v3/rooms/!salon%3Atest/messages?');
    expect(appels.some((u) => u.includes('t2'))).toBe(false); // jamais demandé : arrêt au récent
  });

  it("s'arrête au bout de l'historique", async () => {
    const vide = serveur([{ chunk: [], end: 't1' }]);
    expect(await purgerNotificationsMatrix({ env: ENV, fetchImpl: vide.fetchImpl, maintenant: MAINTENANT })).toBe(0);
    const sansSuite = serveur([{ chunk: [signalement('$a', VIEUX)] }]);
    expect(await purgerNotificationsMatrix({ env: ENV, fetchImpl: sansSuite.fetchImpl, maintenant: MAINTENANT })).toBe(1);
    const sansChunk = serveur([{ end: 't1' }]);
    expect(await purgerNotificationsMatrix({ env: ENV, fetchImpl: sansChunk.fetchImpl, maintenant: MAINTENANT })).toBe(0);
  });

  it('borne le nombre de pages lues', async () => {
    const pages = Array.from({ length: 150 }, (_, i) => ({ chunk: [autre(`$${i}`, VIEUX)], end: `t${i + 1}` }));
    const { fetchImpl, appels } = serveur(pages);
    expect(await purgerNotificationsMatrix({ env: ENV, fetchImpl, maintenant: MAINTENANT })).toBe(0);
    expect(appels.length).toBe(1 + 100);
  });

  it('remonte une erreur du serveur Matrix', async () => {
    const refuse = serveur([], { whoami: true });
    await expect(purgerNotificationsMatrix({ env: ENV, fetchImpl: refuse.fetchImpl, maintenant: MAINTENANT }))
      .rejects.toThrow('HTTP 401 sur /_matrix/client/v3/account/whoami');
    const interdit = serveur([{ chunk: [signalement('$a', VIEUX)] }], { redact: true });
    await expect(purgerNotificationsMatrix({ env: ENV, fetchImpl: interdit.fetchImpl, maintenant: MAINTENANT }))
      .rejects.toThrow('HTTP 403');
  });

  it('prend process.env et le fetch global par défaut', async () => {
    // Sans configuration dans l'environnement de test : rien, sans réseau.
    expect(await purgerNotificationsMatrix()).toBe(0);
  });
});
