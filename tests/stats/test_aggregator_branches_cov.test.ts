/**
 * tests/stats/test_aggregator_branches_cov.test.ts — Branches restantes de
 * `src/lib/stats/aggregator.ts` : sources sans hosts, hosts blancs, item
 * mentionné hors catalogue, types vides, égalités de tri (frSortKey) et
 * `SOURCE_DATE_EPOCH` non finie.
 */
import { describe, it, expect, afterEach } from 'vitest';
import {
  buildStatsSnapshot,
  computeGlobalCounts,
  computeTopGuests,
  computeTopWorks,
  computeTypeDistribution,
  type ItemLike,
  type MentionLike,
} from '../../src/lib/stats/aggregator.ts';

function mention(itemId: string, by?: string | null): MentionLike {
  return {
    itemId,
    sourceRef: { sourceId: 'ubm' },
    recommendedBy: by ?? null,
    status: 'validated',
  };
}
function item(id: string, title: string, types: string[] = ['film']): ItemLike {
  return { id, title, types };
}

describe('buildHostSet — via computeGlobalCounts / computeTopGuests', () => {
  it('source sans champ `hosts` → aucun host filtré', () => {
    const counts = computeGlobalCounts({
      sources: [{ id: 'ubm' }],
      episodes: [],
      mentions: [mention('i1', 'Alice')],
      items: [item('i1', 'A')],
    });
    expect(counts.uniqueGuestsCount).toBe(1);
  });

  it('host réduit à des espaces → ignoré (ne masque personne)', () => {
    const guests = computeTopGuests(
      [mention('i1', 'Alice')],
      [{ id: 'ubm', hosts: ['   ', 'Bob'] }],
    );
    expect(guests.map((g) => g.name)).toEqual(['Alice']);
  });

  it('host déclaré → exclu des invités', () => {
    const guests = computeTopGuests(
      [mention('i1', 'Bob'), mention('i2', 'Alice')],
      [{ id: 'ubm', hosts: ['Bob'] }],
    );
    expect(guests.map((g) => g.name)).toEqual(['Alice']);
  });
});

describe('computeGlobalCounts — item mentionné hors catalogue', () => {
  it("une mention vers un itemId absent des items ne compte pas comme œuvre unique", () => {
    const counts = computeGlobalCounts({
      sources: [{ id: 'ubm', hosts: [] }],
      episodes: [],
      mentions: [mention('i1'), mention('fantome')],
      items: [item('i1', 'A')],
    });
    expect(counts.uniqueWorksCount).toBe(1);
    expect(counts.recommendationsCount).toBe(2);
  });
});

describe('computeTopGuests — égalités de comptage', () => {
  it('à égalité, tri alphabétique insensible à la casse et aux accents', () => {
    const guests = computeTopGuests(
      [mention('i1', 'Bob'), mention('i2', 'Alice'), mention('i3', 'Charlie')],
      [{ id: 'ubm', hosts: [] }],
    );
    expect(guests.map((g) => g.name)).toEqual(['Alice', 'Bob', 'Charlie']);
    expect(guests.map((g) => g.count)).toEqual([1, 1, 1]);
  });

  it('clés de tri identiques (accents) → ordre stable, slugs dédupliqués', () => {
    const guests = computeTopGuests(
      [mention('i1', 'Léa'), mention('i2', 'Lea')],
      [{ id: 'ubm', hosts: [] }],
    );
    expect(guests).toHaveLength(2);
    expect(guests.map((g) => g.name).sort()).toEqual(['Lea', 'Léa']);
    // uniqueSlug doit avoir désambiguïsé les deux `lea`.
    expect(new Set(guests.map((g) => g.slug)).size).toBe(2);
  });
});

describe('computeTopWorks', () => {
  it("item sans type → type 'autre'", () => {
    const works = computeTopWorks([item('i1', 'A', [])], [mention('i1')]);
    expect(works).toEqual([{ id: 'i1', title: 'A', type: 'autre', mentionsCount: 1 }]);
  });

  it('à égalité de mentions, tri alphabétique sur le titre', () => {
    const works = computeTopWorks(
      [item('i1', 'Zèbre'), item('i2', 'Alpha')],
      [mention('i1'), mention('i2')],
    );
    expect(works.map((w) => w.title)).toEqual(['Alpha', 'Zèbre']);
  });

  it('égalité sur plusieurs titres → ordre alphabétique complet', () => {
    // Ordre d'insertion volontairement mélangé : le comparateur doit être
    // exercé dans les deux sens (`ka < kb` et `ka > kb`).
    const titles = ['Delta', 'Alpha', 'Charlie', 'Bravo', 'Écho'];
    const works = computeTopWorks(
      titles.map((t, i) => item(`i${i}`, t)),
      titles.map((_, i) => mention(`i${i}`)),
    );
    expect(works.map((w) => w.title)).toEqual([
      'Alpha',
      'Bravo',
      'Charlie',
      'Delta',
      'Écho',
    ]);
  });

  it('titres à clé de tri identique (accents) → les deux entrées survivent', () => {
    const works = computeTopWorks(
      [item('i1', 'Zèbre'), item('i2', 'Zebre')],
      [mention('i1'), mention('i2')],
    );
    expect(works.map((w) => w.id).sort()).toEqual(['i1', 'i2']);
    expect(works.every((w) => w.mentionsCount === 1)).toBe(true);
  });

  it('mention vers un item inconnu → ignorée', () => {
    const works = computeTopWorks([item('i1', 'A')], [mention('i1'), mention('fantome')]);
    expect(works.map((w) => w.id)).toEqual(['i1']);
  });
});

describe('computeTypeDistribution', () => {
  it("item sans type → compté sous 'autre'", () => {
    expect(computeTypeDistribution([item('i1', 'A', [])], [mention('i1')])).toEqual({
      autre: 1,
    });
  });

  it('à égalité de count, tri alphabétique (film avant livre)', () => {
    const dist = computeTypeDistribution(
      [item('i1', 'A', ['livre']), item('i2', 'B', ['film'])],
      [mention('i1'), mention('i2')],
    );
    expect(Object.keys(dist)).toEqual(['film', 'livre']);
  });

  it('clés de tri identiques (casse) → les deux entrées sont conservées', () => {
    const dist = computeTypeDistribution(
      [item('i1', 'A', ['BD']), item('i2', 'B', ['bd'])],
      [mention('i1'), mention('i2')],
    );
    expect(dist).toEqual({ BD: 1, bd: 1 });
  });

  it('égalité sur plusieurs types → ordre alphabétique complet', () => {
    const types = ['spectacle', 'album', 'livre', 'bd', 'film'];
    const dist = computeTypeDistribution(
      types.map((t, i) => item(`i${i}`, `T${i}`, [t])),
      types.map((_, i) => mention(`i${i}`)),
    );
    expect(Object.keys(dist)).toEqual(['album', 'bd', 'film', 'livre', 'spectacle']);
  });

  it('count différent → tri par count DESC', () => {
    const dist = computeTypeDistribution(
      [item('i1', 'A', ['film']), item('i2', 'B', ['livre']), item('i3', 'C', ['livre'])],
      [mention('i1'), mention('i2'), mention('i3')],
    );
    expect(Object.keys(dist)).toEqual(['livre', 'film']);
  });
});

describe('resolveGeneratedAtFromEnv — via buildStatsSnapshot', () => {
  const saved = {
    epoch: process.env.SOURCE_DATE_EPOCH,
    ts: process.env.RECO_BUILD_TIMESTAMP,
  };
  afterEach(() => {
    if (saved.epoch === undefined) delete process.env.SOURCE_DATE_EPOCH;
    else process.env.SOURCE_DATE_EPOCH = saved.epoch;
    if (saved.ts === undefined) delete process.env.RECO_BUILD_TIMESTAMP;
    else process.env.RECO_BUILD_TIMESTAMP = saved.ts;
  });

  const empty = { sources: [], episodes: [], mentions: [], items: [] };

  it('SOURCE_DATE_EPOCH valide → generatedAt dérivé', () => {
    process.env.SOURCE_DATE_EPOCH = '1700000000';
    delete process.env.RECO_BUILD_TIMESTAMP;
    expect(buildStatsSnapshot(empty).generatedAt).toBe(
      new Date(1_700_000_000_000).toISOString(),
    );
  });

  it('SOURCE_DATE_EPOCH numérique mais non finie → repli sur RECO_BUILD_TIMESTAMP', () => {
    // 401 chiffres : `Number(...)` déborde en Infinity ⇒ `Number.isFinite` faux.
    process.env.SOURCE_DATE_EPOCH = '1' + '0'.repeat(400);
    process.env.RECO_BUILD_TIMESTAMP = '  2026-02-02T00:00:00.000Z  ';
    expect(buildStatsSnapshot(empty).generatedAt).toBe('2026-02-02T00:00:00.000Z');
  });

  it('aucune var → generatedAt temps réel (ISO parseable)', () => {
    delete process.env.SOURCE_DATE_EPOCH;
    delete process.env.RECO_BUILD_TIMESTAMP;
    const iso = buildStatsSnapshot(empty).generatedAt;
    expect(Number.isNaN(new Date(iso).getTime())).toBe(false);
  });

  it('options.generatedAt prioritaire sur les env vars', () => {
    process.env.SOURCE_DATE_EPOCH = '1700000000';
    expect(
      buildStatsSnapshot({ ...empty, options: { generatedAt: '2020-01-01T00:00:00.000Z' } })
        .generatedAt,
    ).toBe('2020-01-01T00:00:00.000Z');
  });
});
