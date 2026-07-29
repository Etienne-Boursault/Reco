/**
 * tests/reports/test_captcha_branches_cov.test.ts — Branches restantes de
 * `src/lib/reports/captcha.ts` : résolution du secret (prod / strict / court),
 * payload signé mais indécodable, réponses numériques ou nulles, `extractJti`
 * sur token malformé et éviction LRU du cache anti-rejeu.
 *
 * ORDRE SIGNIFICATIF : le warning « secret manquant » est one-shot
 * (`_warnedMissingSecret`, module-scope). Le test « production » doit donc
 * s'exécuter avant tout appel qui n'a pas `RECO_QUIET=1`.
 */
import { describe, it, expect, vi } from 'vitest';
import { createHmac } from 'node:crypto';
import {
  generateChallenge,
  verifyChallenge,
  extractJti,
  consumeJti,
  _resetConsumedJti,
} from '../../src/lib/reports/captcha.ts';

const SAVED = {
  NODE_ENV: process.env.NODE_ENV,
  RECO_QUIET: process.env.RECO_QUIET,
  REPORTS_SECRET: process.env.REPORTS_SECRET,
  REPORTS_REQUIRE_SECRET: process.env.REPORTS_REQUIRE_SECRET,
};

function restoreEnv(): void {
  for (const [k, v] of Object.entries(SAVED)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
}

describe('getSecret — résolution du secret', () => {
  it('production sans REPORTS_SECRET → warning une seule fois, fallback dev', () => {
    delete process.env.REPORTS_SECRET;
    delete process.env.REPORTS_REQUIRE_SECRET;
    delete process.env.RECO_QUIET;
    process.env.NODE_ENV = 'production';
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const c = generateChallenge(1_000_000);
      expect(c.token).toMatch(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
      expect(warn).toHaveBeenCalledOnce();
      expect(String(warn.mock.calls[0][0])).toContain(
        'REPORTS_SECRET manquant en production',
      );

      // Le flag `_warnedMissingSecret` rend le warning one-shot.
      warn.mockClear();
      generateChallenge(1_000_000);
      expect(warn).not.toHaveBeenCalled();
    } finally {
      warn.mockRestore();
      restoreEnv();
      process.env.RECO_QUIET = '1';
    }
  });

  it('REPORTS_REQUIRE_SECRET=1 sans secret → throw explicite', () => {
    delete process.env.REPORTS_SECRET;
    process.env.REPORTS_REQUIRE_SECRET = '1';
    process.env.NODE_ENV = 'test';
    try {
      expect(() => generateChallenge(1_000_000)).toThrow(/REPORTS_SECRET manquant ou trop court/);
    } finally {
      restoreEnv();
      process.env.RECO_QUIET = '1';
    }
  });

  it('REPORTS_REQUIRE_SECRET=1 avec un secret < 16 chars → throw', () => {
    process.env.REPORTS_SECRET = 'court';
    process.env.REPORTS_REQUIRE_SECRET = '1';
    try {
      expect(() => generateChallenge(1_000_000)).toThrow(/trop court/);
    } finally {
      restoreEnv();
      process.env.RECO_QUIET = '1';
    }
  });

  it('REPORTS_REQUIRE_SECRET=1 avec un secret ≥ 16 chars → OK', () => {
    process.env.REPORTS_SECRET = 'x'.repeat(32);
    process.env.REPORTS_REQUIRE_SECRET = '1';
    try {
      const c = generateChallenge(1_000_000, () => 0);
      // a=b=1 ⇒ somme 2.
      expect(verifyChallenge(c.token, '2', 1_000_000)).toBe('ok');
    } finally {
      restoreEnv();
      process.env.RECO_QUIET = '1';
    }
  });
});

describe('verifyChallenge — payload signé mais indécodable', () => {
  const SECRET = 'x'.repeat(32);

  function forge(payloadB64: string): string {
    const sig = createHmac('sha256', SECRET).update(payloadB64).digest('base64url');
    return `${payloadB64}.${sig}`;
  }

  function withSecret<T>(fn: () => T): T {
    process.env.REPORTS_SECRET = SECRET;
    delete process.env.REPORTS_REQUIRE_SECRET;
    try {
      return fn();
    } finally {
      restoreEnv();
      process.env.RECO_QUIET = '1';
    }
  }

  it("signature valide mais payload non-JSON → 'invalid'", () => {
    withSecret(() => {
      const token = forge(Buffer.from('pas du json', 'utf8').toString('base64url'));
      expect(verifyChallenge(token, '4', 1_000_000)).toBe('invalid');
    });
  });

  it("signature valide mais payload JSON de mauvaise forme → 'invalid'", () => {
    withSecret(() => {
      const token = forge(
        Buffer.from(JSON.stringify({ nope: 1 }), 'utf8').toString('base64url'),
      );
      expect(verifyChallenge(token, '4', 1_000_000)).toBe('invalid');
    });
  });
});

describe('verifyChallenge — formes de réponse utilisateur', () => {
  it('réponse fournie sous forme de nombre', () => {
    process.env.RECO_QUIET = '1';
    const c = generateChallenge(1_000_000, () => 0);
    expect(verifyChallenge(c.token, 2, 1_000_000)).toBe('ok');
    expect(verifyChallenge(c.token, 99, 1_000_000)).toBe('wrong');
  });

  it("réponse null / undefined → 'wrong' (jamais de crash)", () => {
    const c = generateChallenge(1_000_000, () => 0);
    expect(verifyChallenge(c.token, null, 1_000_000)).toBe('wrong');
    expect(verifyChallenge(c.token, undefined, 1_000_000)).toBe('wrong');
    expect(verifyChallenge(c.token, '   ', 1_000_000)).toBe('wrong');
  });

  it('réponse entourée d espaces → tolérée', () => {
    const c = generateChallenge(1_000_000, () => 0);
    expect(verifyChallenge(c.token, '  2  ', 1_000_000)).toBe('ok');
  });
});

describe('extractJti — tokens malformés', () => {
  it('chaîne vide ou nulle → null', () => {
    expect(extractJti('')).toBeNull();
    expect(extractJti(null as unknown as string)).toBeNull();
  });

  it('token sans point ou avec trop de segments → null', () => {
    expect(extractJti('abcdef')).toBeNull();
    expect(extractJti('a.b.c')).toBeNull();
  });

  it('payload indécodable → null (pas de throw)', () => {
    expect(extractJti(`${Buffer.from('nope', 'utf8').toString('base64url')}.sig`)).toBeNull();
  });

  it('token bien formé → jti non vide', () => {
    process.env.RECO_QUIET = '1';
    const c = generateChallenge(1_000_000);
    expect(extractJti(c.token)).toMatch(/^[A-Za-z0-9_-]{20,}$/);
  });
});

describe('consumeJti — anti-rejeu', () => {
  it('valeur vide ou nulle → false', () => {
    _resetConsumedJti();
    expect(consumeJti(null)).toBe(false);
    expect(consumeJti(undefined)).toBe(false);
    expect(consumeJti('')).toBe(false);
  });

  it('éviction LRU au-delà de 10 000 entrées : le plus ancien redevient libre', () => {
    _resetConsumedJti();
    // 10 001 insertions ⇒ dépassement de JTI_CACHE_MAX (10 000) ⇒ éviction
    // de la plus ancienne entrée (`jti-0`).
    let allFresh = true;
    for (let i = 0; i <= 10_000; i += 1) {
      if (!consumeJti(`jti-${i}`)) allFresh = false;
    }
    expect(allFresh).toBe(true);
    // `jti-1` est toujours dans le cache (rejeu détecté)…
    expect(consumeJti('jti-1')).toBe(false);
    // …mais `jti-0` a été évincé, il repasse donc pour « jamais vu ».
    expect(consumeJti('jti-0')).toBe(true);
    _resetConsumedJti();
  });
});
