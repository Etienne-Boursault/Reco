/**
 * tests/reports/test_rate_limit.test.ts — RateLimiter IP in-memory.
 */
import { describe, it, expect } from 'vitest';
import { createRateLimiter } from '../../src/lib/reports/rateLimit.ts';

describe('rateLimiter', () => {
  it('autorise la première requête, rejette la 2e dans la fenêtre', () => {
    const rl = createRateLimiter(5 * 60 * 1000);
    expect(rl.check('1.2.3.4', 1000)).toBe(true);
    expect(rl.check('1.2.3.4', 1001)).toBe(false);
    expect(rl.check('1.2.3.4', 1002)).toBe(false);
  });

  it('autorise une nouvelle requête après la fenêtre', () => {
    const rl = createRateLimiter(1000);
    expect(rl.check('1.2.3.4', 0)).toBe(true);
    expect(rl.check('1.2.3.4', 999)).toBe(false);
    expect(rl.check('1.2.3.4', 1000)).toBe(true);
  });

  it('rate-limit indépendant par IP', () => {
    const rl = createRateLimiter(1000);
    expect(rl.check('1.1.1.1', 0)).toBe(true);
    expect(rl.check('2.2.2.2', 0)).toBe(true);
    expect(rl.check('1.1.1.1', 100)).toBe(false);
    expect(rl.check('2.2.2.2', 100)).toBe(false);
  });

  it('exempte localhost (IPv4, IPv6, IPv4-mapped)', () => {
    const rl = createRateLimiter(60_000);
    expect(rl.check('127.0.0.1', 0)).toBe(true);
    expect(rl.check('127.0.0.1', 1)).toBe(true);
    expect(rl.check('::1', 0)).toBe(true);
    expect(rl.check('::1', 1)).toBe(true);
    expect(rl.check('::ffff:127.0.0.1', 0)).toBe(true);
  });

  it('hash anonymise (deux check successifs ⇒ size = 1 par IP)', () => {
    const rl = createRateLimiter(1000);
    rl.check('1.2.3.4', 0);
    rl.check('5.6.7.8', 0);
    expect(rl.size()).toBe(2);
    rl.reset();
    expect(rl.size()).toBe(0);
  });
});
