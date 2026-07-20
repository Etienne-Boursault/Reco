/**
 * tests/tracking/test_rate_limit.test.ts — Rate-limit IP /api/click.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRateLimiter, hashIp } from '../../src/lib/tracking/rateLimit.ts';

beforeEach(() => {
  // Salt déterministe pour les tests
  process.env.TRACKING_IP_SALT = 'test-salt-for-tracking-rate-limit-1';
});

describe('createRateLimiter', () => {
  it('accepte jusqu\'à maxHits dans la fenêtre, refuse au-delà', () => {
    const rl = createRateLimiter(60_000, 3);
    expect(rl.check('1.2.3.4', 1000)).toBe(true);
    expect(rl.check('1.2.3.4', 1100)).toBe(true);
    expect(rl.check('1.2.3.4', 1200)).toBe(true);
    expect(rl.check('1.2.3.4', 1300)).toBe(false);
  });

  it('reset à la fin de la fenêtre', () => {
    const rl = createRateLimiter(1000, 2);
    expect(rl.check('1.2.3.4', 1000)).toBe(true);
    expect(rl.check('1.2.3.4', 1500)).toBe(true);
    expect(rl.check('1.2.3.4', 1900)).toBe(false);
    // Après 1s + window → on est de nouveau autorisé
    expect(rl.check('1.2.3.4', 3000)).toBe(true);
  });

  it('exempte localhost (IPv4 et IPv6)', () => {
    const rl = createRateLimiter(60_000, 1);
    expect(rl.check('127.0.0.1', 1000)).toBe(true);
    expect(rl.check('127.0.0.1', 1001)).toBe(true);
    expect(rl.check('::1', 1002)).toBe(true);
    expect(rl.check('::1', 1003)).toBe(true);
  });

  it('IPs distinctes ont des compteurs indépendants', () => {
    const rl = createRateLimiter(60_000, 1);
    expect(rl.check('1.1.1.1', 1000)).toBe(true);
    expect(rl.check('2.2.2.2', 1000)).toBe(true);
    expect(rl.check('1.1.1.1', 1001)).toBe(false);
  });

  it('GC amorti (H25-4) : sweep déclenché par intervalle, pas O(N) chaque check', () => {
    const rl = createRateLimiter(100, 1);
    // Remplir > 512 IPs distinctes au même instant.
    for (let i = 0; i < 800; i++) {
      rl.check(`10.0.${(i >> 8) & 0xff}.${i & 0xff}`, 1000);
    }
    // À ce stade, plusieurs sweeps ont pu se déclencher mais tous les TS
    // restent dans la fenêtre — donc rien n'a été purgé.
    expect(rl.size()).toBeGreaterThan(600);

    // Avance dans le temps : déclencher GC_INTERVAL=256 checks pour
    // forcer un sweep qui purgera enfin les entrées expirées.
    for (let i = 0; i < 300; i++) {
      rl.check(`172.16.${(i >> 8) & 0xff}.${i & 0xff}`, 999_999);
    }
    // Après ce burst, sweep a tourné au moins une fois → les vieilles entrées
    // (t=1000, window=100ms) sont purgées.
    expect(rl.size()).toBeLessThan(400);
  });

  it('B-LOW-16 TRACKING_GC_CAPACITY/INTERVAL configurables via env', async () => {
    process.env.TRACKING_GC_CAPACITY = '4';
    process.env.TRACKING_GC_INTERVAL = '2';
    vi.resetModules();
    const mod = await import('../../src/lib/tracking/rateLimit.ts');
    const rl = mod.createRateLimiter(100, 1);
    for (let i = 0; i < 10; i++) rl.check(`192.168.0.${i}`, 1000);
    for (let i = 0; i < 5; i++) rl.check(`192.168.1.${i}`, 999_999);
    expect(rl.size()).toBeLessThan(10);
    delete process.env.TRACKING_GC_CAPACITY;
    delete process.env.TRACKING_GC_INTERVAL;
  });

  it('B-LOW-16 env invalide → fallback default (pas de crash)', async () => {
    process.env.TRACKING_GC_CAPACITY = 'not-a-number';
    process.env.TRACKING_GC_INTERVAL = '-5';
    vi.resetModules();
    const mod = await import('../../src/lib/tracking/rateLimit.ts');
    expect(() => mod.createRateLimiter(100, 1).check('1.1.1.1', 1000)).not.toThrow();
    delete process.env.TRACKING_GC_CAPACITY;
    delete process.env.TRACKING_GC_INTERVAL;
  });

  it('reset() vide le store', () => {
    const rl = createRateLimiter(60_000, 1);
    rl.check('1.1.1.1', 1000);
    expect(rl.size()).toBeGreaterThan(0);
    rl.reset();
    expect(rl.size()).toBe(0);
    expect(rl.check('1.1.1.1', 1000)).toBe(true);
  });
});

describe('hashIp', () => {
  it('hash déterministe sur 24 hex chars', () => {
    const h1 = hashIp('203.0.113.7');
    const h2 = hashIp('203.0.113.7');
    expect(h1).toBe(h2);
    expect(h1).toMatch(/^[0-9a-f]{24}$/);
  });

  it('hashs distincts pour IPs distinctes', () => {
    expect(hashIp('1.1.1.1')).not.toBe(hashIp('2.2.2.2'));
  });

  it('B-MED-1 HMAC : changer le salt change le hash (résistance attaque préfixe)', () => {
    const prev = process.env.TRACKING_IP_SALT;
    process.env.TRACKING_IP_SALT = 'test-salt-for-tracking-rate-limit-1';
    const a = hashIp('1.1.1.1');
    process.env.TRACKING_IP_SALT = 'autre-salt-de-test-aaaaaa-bbbbbbbb';
    const b = hashIp('1.1.1.1');
    expect(a).not.toBe(b);
    process.env.TRACKING_IP_SALT = prev;
  });
});
