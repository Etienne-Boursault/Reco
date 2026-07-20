/**
 * Test golden cross-stack (R-P1-23, M26-21) — TS side.
 *
 * Vérifie que `buildStatsSnapshot` (TS) produit exactement le snapshot
 * stocké dans `tests/fixtures/stats/golden/snapshot.json`. Le pendant
 * Python (`test_golden_py.py`) consomme les mêmes fichiers — garantit la
 * parité d'exécution TS↔Py.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildStatsSnapshot } from '../../src/lib/stats/aggregator';
import { statsSnapshotSchema } from '../../src/lib/stats/types';

const FIXT = join(process.cwd(), 'tests', 'fixtures', 'stats', 'golden');
const input = JSON.parse(readFileSync(join(FIXT, 'input.json'), 'utf-8'));
const expected = JSON.parse(readFileSync(join(FIXT, 'snapshot.json'), 'utf-8'));

describe('golden cross-stack — TS', () => {
  it('buildStatsSnapshot ≡ snapshot.json', () => {
    const snap = buildStatsSnapshot({
      sources: input.sources,
      episodes: input.episodes,
      mentions: input.mentions,
      items: input.items,
      options: { generatedAt: input.generatedAt },
    });
    // Sanity : doit valider le schéma strict.
    expect(() => statsSnapshotSchema.parse(snap)).not.toThrow();
    expect(snap).toEqual(expected);
  });

  it('tri FR ligature : Œuvre / OEuvre cohérents (M26-21)', () => {
    // L'ordre dépend du NFKD : ni TS ni Py ne décompose la ligature Œ,
    // donc "œuvre" (codepoint 339) > "oeuvre" → OEuvre apparaît avant
    // Œuvre (même count, alpha ASCend).
    const titles = expected.topWorks
      .filter((w: { mentionsCount: number }) => w.mentionsCount === 1)
      .map((w: { title: string }) => w.title);
    expect(titles).toEqual(['OEuvre', 'Œuvre']);
  });

  it('collision slugify : Léa Martin / Lea-Martin → suffix -2 (M26-19)', () => {
    const slugs = expected.topGuests.map((g: { slug: string }) => g.slug);
    expect(slugs).toContain('lea-martin');
    expect(slugs).toContain('lea-martin-2');
  });

  it('monthlyEpisodes remplit les trous (R-P3-30)', () => {
    expect(expected.monthlyEpisodes.map((b: { month: string }) => b.month)).toEqual([
      '2024-01',
      '2024-02',
      '2024-03',
    ]);
  });
});
