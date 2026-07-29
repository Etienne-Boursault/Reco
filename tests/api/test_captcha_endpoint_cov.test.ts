/**
 * tests/api/test_captcha_endpoint_cov.test.ts
 *
 * Endpoint `GET /api/captcha` (`src/pages/api/captcha.ts`).
 *
 * Contrat vérifié :
 *  - 200 + JSON `{ token, question }` (et rien d'autre — pas de fuite de la
 *    réponse en clair) ;
 *  - `Cache-Control: no-store` : un cache CDN casserait l'anti-rejeu (jti à
 *    usage unique) ;
 *  - défi FRAIS à chaque appel (token différent) ;
 *  - le token émis est réellement vérifiable par `verifyChallenge` avec la
 *    réponse de la question posée — c'est tout l'intérêt de l'endpoint.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { GET } from '../../src/pages/api/captcha.js';
import { verifyChallenge } from '../../src/lib/reports/captcha.js';

beforeAll(() => {
  // Évite le warning « REPORTS_SECRET manquant » dans la sortie de test.
  process.env.RECO_QUIET = '1';
});

function ctx(): Parameters<typeof GET>[0] {
  return {} as never;
}

async function call(): Promise<{ res: Response; body: Record<string, unknown> }> {
  const res = (await GET(ctx())) as Response;
  const body = (await res.clone().json()) as Record<string, unknown>;
  return { res, body };
}

describe('GET /api/captcha', () => {
  it('répond 200 en JSON UTF-8', async () => {
    const { res } = await call();
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
  });

  it("interdit toute mise en cache (anti-rejeu du jti)", async () => {
    const { res } = await call();
    expect(res.headers.get('Cache-Control')).toBe('no-store, max-age=0');
  });

  it('expose exactement { token, question }', async () => {
    const { body } = await call();
    expect(Object.keys(body).sort()).toEqual(['question', 'token']);
    expect(typeof body.token).toBe('string');
    expect(body.question).toMatch(/^Combien font \d \+ \d \?$/);
  });

  it('émet un token signé (payload.signature) sans réponse en clair', async () => {
    const { body } = await call();
    const token = body.token as string;
    const parts = token.split('.');
    expect(parts).toHaveLength(2);

    const payload = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8')) as Record<
      string,
      unknown
    >;
    // La réponse n'est jamais stockée en clair (fix C16-1) : seulement un hash.
    expect(Object.keys(payload).sort()).toEqual(['exp', 'h', 'jti']);
    expect(typeof payload.h).toBe('string');
  });

  it('régénère un défi frais à chaque appel', async () => {
    const a = await call();
    const b = await call();
    // Le jti est aléatoire : deux tokens consécutifs ne peuvent pas coïncider.
    expect(a.body.token).not.toBe(b.body.token);
  });

  it('émet un token que verifyChallenge accepte avec la bonne réponse', async () => {
    const { body } = await call();
    const m = /(\d) \+ (\d)/.exec(body.question as string);
    expect(m).not.toBeNull();
    const sum = Number(m![1]) + Number(m![2]);

    expect(verifyChallenge(body.token as string, sum)).toBe('ok');
    expect(verifyChallenge(body.token as string, sum + 1)).toBe('wrong');
  });
});
