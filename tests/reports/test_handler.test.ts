/**
 * tests/reports/test_handler.test.ts — Endpoint POST `/api/report` (handler).
 *
 * Couvre toutes les couches d'acceptation (cf. handler.ts) :
 *  - origin mismatch → 403
 *  - honeypot rempli → 204
 *  - payload invalide → 400
 *  - captcha wrong → 400
 *  - rate-limit hit → 429
 *  - happy path → 200 + fichier écrit
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { mkdtempSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { handleReport } from '../../src/lib/reports/handler.ts';
import { generateChallenge } from '../../src/lib/reports/captcha.ts';
import { createRateLimiter } from '../../src/lib/reports/rateLimit.ts';
import { listReports } from '../../src/lib/reports/storage.ts';

let CWD: string;
const SELF = 'https://reco.example';

function validForm(): Record<string, string> {
  const c = generateChallenge(1_000_000);
  // RNG indéterministe → on parse la question pour extraire a,b et calculer
  // la réponse attendue. Robuste à la pluralité des challenges générés.
  return {
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    category: 'error',
    details: 'Le titre comporte une faute de frappe.',
    name: 'Alice',
    email: 'alice@example.org',
    wantCredit: 'on',
    website: '',
    captchaToken: c.token,
    captchaAnswer: String(extractAnswer(c.question)),
  };
}

function extractAnswer(q: string): number {
  const m = q.match(/(\d) \+ (\d)/);
  if (!m) throw new Error(`Question inattendue : ${q}`);
  return Number(m[1]) + Number(m[2]);
}

beforeEach(() => {
  CWD = mkdtempSync(join(tmpdir(), 'reco-handler-'));
  process.env.NODE_ENV = 'test';
});

describe('handleReport', () => {
  it('happy path : 200, fichier écrit, id renvoyé', () => {
    const fd = validForm();
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(60_000),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.id).toMatch(/^rep-[0-9a-f-]{36}$/);

    const reports = listReports('un-bon-moment', { cwd: CWD });
    expect(reports).toHaveLength(1);
    expect(reports[0]).toMatchObject({
      sourceId: 'un-bon-moment',
      recoId: 'ubm-0001',
      category: 'error',
      status: 'pending',
      submitter: { name: 'Alice', email: 'alice@example.org', wantCredit: true },
    });
  });

  it('origin mismatch → 403', () => {
    const res = handleReport({
      formData: validForm(),
      origin: 'https://evil.example',
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res.status).toBe(403);
  });

  it('origin absent → 403', () => {
    const res = handleReport({
      formData: validForm(),
      origin: null,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res.status).toBe(403);
  });

  it('honeypot rempli → 204 silencieux, aucun fichier écrit', () => {
    const fd = validForm();
    fd.website = 'http://buy-cheap-pills.example';
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res.status).toBe(204);
    expect(listReports('un-bon-moment', { cwd: CWD })).toHaveLength(0);
  });

  it('captcha wrong → 400', () => {
    const fd = validForm();
    fd.captchaAnswer = '999';
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/captcha/);
  });

  it('payload invalide (catégorie inconnue) → 400', () => {
    const fd = validForm();
    fd.category = 'nope';
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res.status).toBe(400);
  });

  it('payload invalide (details trop courts) → 400', () => {
    const fd = validForm();
    fd.details = 'ko';
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res.status).toBe(400);
  });

  it('rate-limit IP → 429 à la 2e requête', () => {
    const rl = createRateLimiter(60_000);
    const ip = '198.51.100.42';
    const first = handleReport({
      formData: validForm(),
      origin: SELF,
      selfOrigin: SELF,
      ip,
      rateLimiter: rl,
      cwd: CWD,
      now: 1_000_000,
    });
    expect(first.status).toBe(200);
    const second = handleReport({
      formData: validForm(),
      origin: SELF,
      selfOrigin: SELF,
      ip,
      rateLimiter: rl,
      cwd: CWD,
      now: 1_001_000,
    });
    expect(second.status).toBe(429);
  });

  it('rejette email invalide → 400', () => {
    const fd = validForm();
    fd.email = 'pas-un-email';
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(res.status).toBe(400);
  });

  it('accepte email + name vides (champs optionnels)', () => {
    const fd = validForm();
    fd.email = '';
    fd.name = '';
    delete fd.wantCredit;
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.7',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(res.status).toBe(200);
    const reports = listReports('un-bon-moment', { cwd: CWD });
    expect(reports[0].submitter).toEqual({ wantCredit: false });
  });
});
