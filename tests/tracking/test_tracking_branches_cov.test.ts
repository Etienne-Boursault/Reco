/**
 * tests/tracking/test_tracking_branches_cov.test.ts — Branches restantes de
 * `src/lib/tracking/{rateLimit,settings,validator}.ts`.
 *
 * ORDRE SIGNIFICATIF : le warning « TRACKING_IP_SALT manquant » est one-shot
 * (`_saltWarned`, module-scope) — le bloc rateLimit doit rester en tête.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { hashIp, createRateLimiter } from '../../src/lib/tracking/rateLimit.ts';
import { fromSourceExtra, categorizeUrl } from '../../src/lib/tracking/settings.ts';
import { sanitizeRef } from '../../src/lib/tracking/validator.ts';

const SAVED_SALT = process.env.TRACKING_IP_SALT;
const SAVED_QUIET = process.env.RECO_QUIET;

function restoreEnv(): void {
  if (SAVED_SALT === undefined) delete process.env.TRACKING_IP_SALT;
  else process.env.TRACKING_IP_SALT = SAVED_SALT;
  if (SAVED_QUIET === undefined) delete process.env.RECO_QUIET;
  else process.env.RECO_QUIET = SAVED_QUIET;
}

describe('tracking/rateLimit — salt de repli', () => {
  afterEach(() => {
    restoreEnv();
    vi.restoreAllMocks();
  });

  it('TRACKING_IP_SALT absent → warning one-shot puis salt de boot', () => {
    delete process.env.TRACKING_IP_SALT;
    delete process.env.RECO_QUIET;
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    const h1 = hashIp('192.0.2.1');
    expect(h1).toMatch(/^[0-9a-f]{24}$/);
    expect(warn).toHaveBeenCalledOnce();
    expect(String(warn.mock.calls[0][0])).toContain('TRACKING_IP_SALT manquant');

    // Le salt de boot est stable au sein du process…
    expect(hashIp('192.0.2.1')).toBe(h1);
    // …et le warning ne se répète pas.
    expect(warn).toHaveBeenCalledOnce();
  });

  it('TRACKING_IP_SALT trop court (< 16) → repli sur le salt de boot', () => {
    process.env.RECO_QUIET = '1';
    delete process.env.TRACKING_IP_SALT;
    const boot = hashIp('192.0.2.2');
    process.env.TRACKING_IP_SALT = 'court';
    expect(hashIp('192.0.2.2')).toBe(boot);
  });

  it('TRACKING_IP_SALT ≥ 16 → hash distinct du salt de boot', () => {
    process.env.RECO_QUIET = '1';
    delete process.env.TRACKING_IP_SALT;
    const boot = hashIp('192.0.2.3');
    process.env.TRACKING_IP_SALT = 'un-salt-explicite-assez-long';
    expect(hashIp('192.0.2.3')).not.toBe(boot);
  });

  it('reset() vide le store', () => {
    process.env.TRACKING_IP_SALT = 'un-salt-explicite-assez-long';
    const rl = createRateLimiter(1000, 1);
    expect(rl.check('192.0.2.4', 1000)).toBe(true);
    expect(rl.check('192.0.2.4', 1100)).toBe(false);
    rl.reset();
    expect(rl.size()).toBe(0);
    expect(rl.check('192.0.2.4', 1100)).toBe(true);
  });
});

describe('fromSourceExtra — categoryOverrides dégradés', () => {
  afterEach(() => {
    restoreEnv();
    vi.restoreAllMocks();
  });

  it('catégorie inconnue → ignorée avec un warning', () => {
    delete process.env.RECO_QUIET;
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const s = fromSourceExtra({
      tracking: { categoryOverrides: { 'x.example': 'Spotify', 'y.example': 'spotify' } },
    });
    expect(s.categoryOverrides).toEqual({ 'y.example': 'spotify' });
    expect(warn).toHaveBeenCalledOnce();
    expect(String(warn.mock.calls[0][0])).toContain('x.example');
  });

  it('RECO_QUIET=1 → catégorie inconnue ignorée en silence', () => {
    process.env.RECO_QUIET = '1';
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const s = fromSourceExtra({ tracking: { categoryOverrides: { 'x.example': 42 } } });
    expect(s.categoryOverrides).toEqual({});
    expect(warn).not.toHaveBeenCalled();
  });

  it('clé de host vide → ignorée', () => {
    process.env.RECO_QUIET = '1';
    const s = fromSourceExtra({ tracking: { categoryOverrides: { '': 'spotify' } } });
    expect(s.categoryOverrides).toEqual({});
  });

  it('hosts normalisés en minuscules', () => {
    process.env.RECO_QUIET = '1';
    const s = fromSourceExtra({ tracking: { categoryOverrides: { 'X.Example': 'imdb' } } });
    expect(s.categoryOverrides).toEqual({ 'x.example': 'imdb' });
  });

  it('extra absent / non-objet / sans `tracking` → defaults', () => {
    expect(fromSourceExtra(undefined).windowMs).toBe(60_000);
    expect(fromSourceExtra('nope').maxHits).toBe(60);
    expect(fromSourceExtra({}).maxHits).toBe(60);
    expect(fromSourceExtra({ tracking: 'nope' }).maxHits).toBe(60);
  });
});

describe('categorizeUrl — branches restantes', () => {
  it('URL valide mais sans hostname → other', () => {
    expect(categorizeUrl('mailto:contact@example.org')).toBe('other');
    expect(categorizeUrl('file:///tmp/x.html')).toBe('other');
  });

  it('URL non parseable → other', () => {
    expect(categorizeUrl('pas une url')).toBe('other');
  });

  it('override non matchant → on retombe sur le mapping par défaut', () => {
    expect(categorizeUrl('https://www.imdb.com/title/tt1', { 'autre.fr': 'tmdb' })).toBe('imdb');
  });

  it('override matchant en exact ou en sous-domaine', () => {
    expect(categorizeUrl('https://shop.example', { 'shop.example': 'other' })).toBe('other');
    expect(categorizeUrl('https://fr.boutique.fr', { 'boutique.fr': 'spotify' })).toBe('spotify');
  });

  it('host inconnu → other', () => {
    expect(categorizeUrl('https://exemple-inconnu.fr/x')).toBe('other');
  });

  it('fallback substring « librairie »', () => {
    expect(categorizeUrl('https://www.librairie-du-coin.fr/livre/1')).toBe('library');
  });
});

describe('sanitizeRef — branches restantes', () => {
  it('ref composée uniquement de NULL bytes → null', () => {
    expect(sanitizeRef('\x00\x00')).toBeNull();
  });

  it('ref vide / nulle → null', () => {
    expect(sanitizeRef('')).toBeNull();
    expect(sanitizeRef(null)).toBeNull();
    expect(sanitizeRef(undefined)).toBeNull();
  });

  it("URL absolue sans pathname (schéma non spécial) → '/'", () => {
    // `new URL('foo:').pathname` vaut '' ⇒ la garde `|| '/'` s'applique.
    expect(sanitizeRef('foo:')).toBe('/');
  });

  it('URL absolue → path seul (query et hash retirés)', () => {
    expect(sanitizeRef('https://x.fr/a/b?utm=1#frag')).toBe('/a/b');
  });

  it('chemin relatif conservé, chemin non préfixé par / rejeté', () => {
    expect(sanitizeRef('/ubm/episode/42')).toBe('/ubm/episode/42');
    expect(sanitizeRef('ubm/episode/42')).toBeNull();
  });

  it('NULL byte à l intérieur d une URL absolue → strippé', () => {
    expect(sanitizeRef('https://x.fr/a\x00b')).toBe('/ab');
  });
});
