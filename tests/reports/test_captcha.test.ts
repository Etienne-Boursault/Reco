/**
 * tests/reports/test_captcha.test.ts — Math captcha HMAC.
 *
 * Couvre :
 *  - génération + vérification happy path,
 *  - mauvaise réponse,
 *  - token expiré (now+TTL),
 *  - signature trafiquée,
 *  - token mal-formé,
 *  - secret env override.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  generateChallenge,
  verifyChallenge,
  consumeJti,
  extractJti,
  _resetConsumedJti,
} from '../../src/lib/reports/captcha.ts';

beforeEach(() => {
  // S'assurer qu'on n'est PAS en production (sinon le secret manquant throw).
  process.env.NODE_ENV = 'test';
  process.env.RECO_QUIET = '1';
  _resetConsumedJti();
});

describe('captcha math', () => {
  it('génère une question et un token signé', () => {
    const c = generateChallenge();
    expect(c.question).toMatch(/Combien font \d \+ \d \?/);
    expect(c.token).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
  });

  it("verifyChallenge('ok') pour la bonne réponse", () => {
    // RNG déterministe : a=3, b=4 ⇒ somme=7.
    const rng = () => 0.3; // floor(0.3*9)=2 → 1+2=3 ; appelé deux fois.
    const c = generateChallenge(1_000_000, rng);
    // a=3, b=3 (les deux 0.3) → sum=6
    expect(verifyChallenge(c.token, '6', 1_000_000)).toBe('ok');
  });

  it("verifyChallenge('wrong') pour la mauvaise réponse", () => {
    const c = generateChallenge(0, () => 0);
    // a=b=1, sum=2 ; on envoie 99 → wrong.
    expect(verifyChallenge(c.token, '99', 0)).toBe('wrong');
  });

  it("verifyChallenge('expired') au-delà du TTL", () => {
    const c = generateChallenge(0);
    // Bien après l'expiry (>365j). On simule un now > exp.
    expect(verifyChallenge(c.token, '5', 2 * 365 * 24 * 60 * 60 * 1000)).toBe('expired');
  });

  it("verifyChallenge('invalid') si signature trafiquée", () => {
    const c = generateChallenge();
    const [payload] = c.token.split('.');
    const tampered = `${payload}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`;
    expect(verifyChallenge(tampered, '5')).toBe('invalid');
  });

  it("verifyChallenge('invalid') si token mal-formé", () => {
    expect(verifyChallenge(null, '5')).toBe('invalid');
    expect(verifyChallenge('', '5')).toBe('invalid');
    expect(verifyChallenge('nodot', '5')).toBe('invalid');
    expect(verifyChallenge('a.b.c', '5')).toBe('invalid');
  });

  it("verifyChallenge('wrong') si réponse non-numérique", () => {
    const c = generateChallenge();
    expect(verifyChallenge(c.token, 'abc')).toBe('wrong');
    expect(verifyChallenge(c.token, '')).toBe('wrong');
  });

  it('C16-1 — payload décodé ne révèle PAS la réponse en clair', () => {
    // Sum=2 ; on vérifie que "2" n'apparaît PAS dans le JSON décodé du payload.
    const c = generateChallenge(0, () => 0);
    const [payloadB64] = c.token.split('.');
    const json = Buffer.from(payloadB64, 'base64url').toString('utf8');
    const obj = JSON.parse(json);
    // Le payload contient h (hash), exp, jti — pas de champ 'a' avec la réponse.
    expect(obj).toHaveProperty('h');
    expect(obj).toHaveProperty('exp');
    expect(obj).toHaveProperty('jti');
    expect(obj).not.toHaveProperty('a');
    // Le hash ne doit pas être trivialement = "2".
    expect(obj.h).not.toBe('2');
    expect(obj.h).not.toBe(2);
    expect(String(obj.h).length).toBeGreaterThan(20); // base64url de sha256
  });

  it('C16-3 — TTL court (4h) — un token à 5h est expiré', () => {
    const c = generateChallenge(0);
    // 5h > 4h TTL ⇒ expired.
    expect(verifyChallenge(c.token, '5', 5 * 60 * 60 * 1000)).toBe('expired');
  });

  it('C16-3 — consumeJti : première fois OK, seconde fois refusée', () => {
    const c = generateChallenge();
    const jti = extractJti(c.token);
    expect(jti).toBeTruthy();
    expect(consumeJti(jti)).toBe(true);
    expect(consumeJti(jti)).toBe(false);
  });

  it('C16-3 — tokens successifs ont des jti distincts', () => {
    const c1 = generateChallenge();
    const c2 = generateChallenge();
    expect(extractJti(c1.token)).not.toBe(extractJti(c2.token));
  });

  it('change de signature quand REPORTS_SECRET change', () => {
    process.env.REPORTS_SECRET = 'a'.repeat(32);
    const c1 = generateChallenge(0, () => 0);
    process.env.REPORTS_SECRET = 'b'.repeat(32);
    // Le token signé sous la 1ère clé doit être rejeté par la 2nde.
    expect(verifyChallenge(c1.token, '2', 0)).toBe('invalid');
    delete process.env.REPORTS_SECRET;
  });
});
