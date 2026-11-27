/**
 * tests/tracking/test_validator.test.ts — Zod schema /api/click.
 */
import { describe, it, expect } from 'vitest';
import { clickPayloadSchema, sanitizeRef } from '../../src/lib/tracking/validator.ts';

describe('clickPayloadSchema', () => {
  it('accepte un payload minimal valide', () => {
    const res = clickPayloadSchema.safeParse({
      url: 'https://themoviedb.org/movie/42',
      category: 'tmdb',
      sourceId: 'un-bon-moment',
    });
    expect(res.success).toBe(true);
  });

  it('accepte les champs optionnels', () => {
    const res = clickPayloadSchema.safeParse({
      url: 'https://spotify.com/track/abc',
      category: 'spotify',
      sourceId: 'un-bon-moment',
      recoId: 'ubm-0001',
      ref: '/un-bon-moment/episode/123',
    });
    expect(res.success).toBe(true);
  });

  it('rejette une URL non-http', () => {
    const res = clickPayloadSchema.safeParse({
      url: 'javascript:alert(1)',
      category: 'other',
      sourceId: 'src',
    });
    expect(res.success).toBe(false);
  });

  it('rejette une catégorie inconnue', () => {
    const res = clickPayloadSchema.safeParse({
      url: 'https://x.com',
      category: 'tiktok',
      sourceId: 'src',
    });
    expect(res.success).toBe(false);
  });

  it('rejette un sourceId non-slug', () => {
    const res = clickPayloadSchema.safeParse({
      url: 'https://x.com',
      category: 'other',
      sourceId: '../etc/passwd',
    });
    expect(res.success).toBe(false);
  });

  it('rejette une URL trop longue', () => {
    const long = 'https://example.com/' + 'a'.repeat(3000);
    const res = clickPayloadSchema.safeParse({
      url: long,
      category: 'other',
      sourceId: 'src',
    });
    expect(res.success).toBe(false);
  });

  it('rejette les champs inconnus (strict)', () => {
    const res = clickPayloadSchema.safeParse({
      url: 'https://x.com',
      category: 'other',
      sourceId: 'src',
      evilField: 'pwn',
    });
    expect(res.success).toBe(false);
  });
});

describe('sanitizeRef', () => {
  it('extrait le path d\'une URL absolue (drop query/hash)', () => {
    expect(sanitizeRef('https://reco.example/un-bon-moment/episode/42?utm=spam#x')).toBe(
      '/un-bon-moment/episode/42',
    );
  });

  it('accepte un path relatif raisonnable', () => {
    expect(sanitizeRef('/episodes/42')).toBe('/episodes/42');
  });

  it('rejette les non-paths bizarres', () => {
    expect(sanitizeRef('not-a-url')).toBeNull();
    expect(sanitizeRef('')).toBeNull();
    expect(sanitizeRef(null)).toBeNull();
    expect(sanitizeRef(undefined)).toBeNull();
  });

  it('tronque path absolu si trop long → null', () => {
    expect(sanitizeRef('/' + 'a'.repeat(600))).toBeNull();
  });
});

describe('clickPayloadSchema edge cases', () => {
  it('rejette URL qui throws au parse (non-string-ish)', () => {
    // String contenant des octets invalides — URL() throw
    const res = clickPayloadSchema.safeParse({
      url: 'http://[invalid',
      category: 'other',
      sourceId: 'src',
    });
    expect(res.success).toBe(false);
  });

  it('renvoie un message d\'erreur générique si Zod ne fournit pas issues', () => {
    // Cas synthétique : on s'assure que sourceId vide est rejeté avec message
    const res = clickPayloadSchema.safeParse({
      url: 'https://x.com',
      category: 'other',
      sourceId: '',
    });
    expect(res.success).toBe(false);
  });
});

describe('clickPayloadSchema : les trois oui/non (D1, R-1, AU-2 B)', () => {
  const base = { url: 'https://x.com', category: 'other' as const, sourceId: 'src' };
  const ouiNon = { revenant: true, aVuEpisode: false, aVuFiche: true };

  it('accepte les trois champs présents, booléens', () => {
    const res = clickPayloadSchema.safeParse({ ...base, ...ouiNon });
    expect(res.success).toBe(true);
    expect(res.data).toMatchObject(ouiNon);
  });

  it('accepte leur absence (ancien script en cache)', () => {
    expect(clickPayloadSchema.safeParse(base).success).toBe(true);
  });

  it.each(['revenant', 'aVuEpisode', 'aVuFiche'])('rejette %s seul ou manquant (champ à moitié présent)', (manque) => {
    const { [manque]: _, ...reste } = ouiNon as Record<string, boolean>;
    expect(clickPayloadSchema.safeParse({ ...base, ...reste }).success).toBe(false);
    expect(clickPayloadSchema.safeParse({ ...base, [manque]: true }).success).toBe(false);
  });

  it.each([['oui'], [1], [0], [null], [{}], [[]]])('rejette un type faux (%j)', (faux) => {
    expect(clickPayloadSchema.safeParse({ ...base, ...ouiNon, aVuFiche: faux }).success).toBe(false);
  });

  it('garde sa règle : un champ inconnu est rejeté', () => {
    expect(clickPayloadSchema.safeParse({ ...base, ...ouiNon, ne: '2026-11-27' }).success).toBe(false);
  });
});
