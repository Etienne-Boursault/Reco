/**
 * Tests `src/lib/work/similarity` — SimilarWorksProvider (ADR 0044).
 */
import { describe, it, expect } from 'vitest';
import {
  creatorBasedProvider,
  embeddingsBasedProvider,
  compositeProvider,
  getSimilarWorksProvider,
  type SimilarWorksData,
  type SimilarWorksDataLoader,
} from '../../src/lib/work/similarity';
import { similarByCreator, type ItemLike } from '../../src/lib/work/aggregator';

function item(id: string, over: Partial<ItemLike> = {}): ItemLike {
  return { id, title: `Title ${id}`, types: ['film'], ...over };
}

const fixtures: ItemLike[] = [
  item('current', { creator: 'Bong Joon-ho' }),
  item('other-bong-1', { creator: 'Bong Joon-ho' }),
  item('other-bong-2', { creator: 'BONG JOON-HO ' }),
  item('mortel', { creator: 'Frédéric Garcia' }),
  item('orphan', { creator: undefined }),
];

describe('creatorBasedProvider', () => {
  it('retourne les items du même créateur (case-insensible)', () => {
    const current = fixtures[0];
    const candidates = fixtures.slice(1);
    const out = creatorBasedProvider.findSimilar(current, candidates);
    expect(out.map((h) => h.id)).toEqual(['other-bong-1', 'other-bong-2']);
    expect(out.every((h) => h.reason === 'creator')).toBe(true);
    expect(out[0].score).toBeUndefined();
  });

  it('exclut l’item courant', () => {
    const current = fixtures[0];
    const out = creatorBasedProvider.findSimilar(current, fixtures);
    expect(out.find((h) => h.id === 'current')).toBeUndefined();
  });

  it('retourne [] si l’item courant n’a pas de créateur', () => {
    const out = creatorBasedProvider.findSimilar(item('x'), fixtures);
    expect(out).toEqual([]);
  });

  it('respecte limit', () => {
    const out = creatorBasedProvider.findSimilar(
      fixtures[0],
      fixtures.slice(1),
      { limit: 1 },
    );
    expect(out).toHaveLength(1);
  });
});

describe('embeddingsBasedProvider', () => {
  const dataFor = (data: SimilarWorksData | null): SimilarWorksDataLoader => () => data;

  const data: SimilarWorksData = {
    schemaVersion: 1,
    source: 's',
    model: 'm',
    k: 6,
    generated_at: '2026-06-12T00:00:00Z',
    items: {
      current: [
        { id: 'mortel', score: 0.91 },
        { id: 'other-bong-1', score: 0.84 },
        { id: 'ghost', score: 0.7 }, // référencé mais absent des candidates
      ],
    },
  };

  it('résout les voisins depuis les candidates', () => {
    const provider = embeddingsBasedProvider('s', dataFor(data));
    const out = provider.findSimilar(fixtures[0], fixtures);
    expect(out.map((h) => h.id)).toEqual(['mortel', 'other-bong-1']);
    expect(out[0].score).toBe(0.91);
    expect(out[0].reason).toBe('embeddings');
  });

  it('retourne [] si dataLoader → null', () => {
    const provider = embeddingsBasedProvider('s', dataFor(null));
    expect(provider.findSimilar(fixtures[0], fixtures)).toEqual([]);
  });

  it('retourne [] si l’item courant n’a pas d’entrée', () => {
    const provider = embeddingsBasedProvider('s', dataFor(data));
    expect(provider.findSimilar(item('autre'), fixtures)).toEqual([]);
  });

  it('respecte limit', () => {
    const provider = embeddingsBasedProvider('s', dataFor(data));
    const out = provider.findSimilar(fixtures[0], fixtures, { limit: 1 });
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('mortel');
  });

  it('ignore l’item courant même s’il apparaît dans les voisins', () => {
    const selfData: SimilarWorksData = {
      ...data,
      items: { current: [{ id: 'current', score: 1.0 }, { id: 'mortel', score: 0.9 }] },
    };
    const provider = embeddingsBasedProvider('s', dataFor(selfData));
    const out = provider.findSimilar(fixtures[0], fixtures);
    expect(out.map((h) => h.id)).toEqual(['mortel']);
  });
});

describe('compositeProvider', () => {
  it('utilise embeddings quand non vide', () => {
    const data: SimilarWorksData = {
      schemaVersion: 1, source: 's', model: 'm', k: 6,
      generated_at: '', items: { current: [{ id: 'mortel', score: 0.9 }] },
    };
    const provider = compositeProvider(
      embeddingsBasedProvider('s', () => data),
      creatorBasedProvider,
    );
    const out = provider.findSimilar(fixtures[0], fixtures);
    expect(out[0].reason).toBe('embeddings');
  });

  it('fallback creator si embeddings retourne []', () => {
    const provider = compositeProvider(
      embeddingsBasedProvider('s', () => null),
      creatorBasedProvider,
    );
    const out = provider.findSimilar(fixtures[0], fixtures);
    expect(out[0].reason).toBe('creator');
  });
});

describe('getSimilarWorksProvider', () => {
  it('renvoie le creator-based si pas de dataLoader', () => {
    const provider = getSimilarWorksProvider('s');
    const out = provider.findSimilar(fixtures[0], fixtures.slice(1));
    expect(out.every((h) => h.reason === 'creator')).toBe(true);
  });

  it('renvoie le composite si dataLoader fourni', () => {
    const data: SimilarWorksData = {
      schemaVersion: 1, source: 's', model: 'm', k: 6,
      generated_at: '', items: { current: [{ id: 'mortel', score: 0.9 }] },
    };
    const provider = getSimilarWorksProvider('s', { dataLoader: () => data });
    const out = provider.findSimilar(fixtures[0], fixtures);
    expect(out[0].reason).toBe('embeddings');
  });
});

describe('similarByCreator (rétro-compat ADR 0044)', () => {
  it('reste exporté depuis aggregator avec la signature historique', () => {
    const out = similarByCreator(fixtures[0], fixtures.slice(1));
    expect(out.map((it) => it.id)).toEqual(['other-bong-1', 'other-bong-2']);
    // Vérifie qu'on retourne des ItemLike, pas des SimilarWork.
    expect(out[0].types).toEqual(['film']);
  });

  it('respecte limit historique (3 par défaut)', () => {
    const many = Array.from({ length: 5 }, (_, i) =>
      item(`x${i}`, { creator: 'Bong Joon-ho' }),
    );
    const out = similarByCreator(fixtures[0], many);
    expect(out).toHaveLength(3);
  });
});
