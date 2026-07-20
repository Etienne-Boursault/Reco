/**
 * Tests d'agrégation cross-épisodes (lib/work/aggregator).
 */
import { describe, it, expect } from 'vitest';
import {
  buildWorkIndex,
  isVisibleMention,
  similarByCreator,
  workExternalLinks,
  youtubeDeepLink,
  type ItemLike,
  type MentionLike,
  type EpisodeLike,
} from '../../src/lib/work/aggregator';

function item(id: string, over: Partial<ItemLike> = {}): ItemLike {
  return { id, title: id, types: ['film'], ...over };
}
function mention(
  id: string,
  itemId: string,
  over: Partial<MentionLike> = {},
): MentionLike {
  return {
    id,
    itemId,
    sourceRef: { sourceId: 'ubm', episodeGuid: `ep-${id}` },
    kind: 'reco',
    status: 'validated',
    ...over,
  };
}
function ep(guid: string, date?: string): EpisodeLike {
  return { guid, title: `Ép ${guid}`, date: date ? new Date(date) : undefined };
}

describe('isVisibleMention', () => {
  it('cache discarded', () => {
    expect(isVisibleMention(mention('m1', 'i1', { status: 'discarded' }))).toBe(false);
  });
  it('garde draft et validated', () => {
    expect(isVisibleMention(mention('m1', 'i1', { status: 'draft' }))).toBe(true);
    expect(isVisibleMention(mention('m1', 'i1', { status: 'validated' }))).toBe(true);
  });
});

describe('buildWorkIndex', () => {
  const items = [item('i1', { title: 'Parasite' }), item('i2', { title: 'Mortel' })];
  const episodes = [ep('ep-m1', '2026-01-01'), ep('ep-m2', '2026-03-01'), ep('ep-m3', '2026-05-01')];

  it('groupe les mentions par itemId pour la source courante', () => {
    const mentions = [
      mention('m1', 'i1'),
      mention('m2', 'i1'),
      mention('m3', 'i2'),
      mention('m4', 'i1', { sourceRef: { sourceId: 'other', episodeGuid: 'ep-m4' } }),
    ];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    expect(idx.size).toBe(2);
    expect(idx.get('i1')!.mentionCount).toBe(2);
    expect(idx.get('i2')!.mentionCount).toBe(1);
  });

  it('ignore les mentions discarded', () => {
    const mentions = [
      mention('m1', 'i1'),
      mention('m2', 'i1', { status: 'discarded' }),
    ];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    expect(idx.get('i1')!.mentionCount).toBe(1);
  });

  it('ignore les mentions vers un item inconnu', () => {
    const mentions = [mention('m1', 'orphan')];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    expect(idx.size).toBe(0);
  });

  it('trie les mentions par date d’épisode DESC', () => {
    const mentions = [
      mention('m1', 'i1'), // 2026-01-01
      mention('m2', 'i1'), // 2026-03-01 (ep-m2)
      mention('m3', 'i1'), // 2026-05-01 (ep-m3)
    ];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    const order = idx.get('i1')!.mentions.map((jm) => jm.mention.id);
    expect(order).toEqual(['m3', 'm2', 'm1']);
  });

  it('expose lastMentionedAt = date la plus récente', () => {
    const mentions = [mention('m1', 'i1'), mention('m2', 'i1')];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    expect(idx.get('i1')!.lastMentionedAt?.toISOString().slice(0, 10)).toBe(
      '2026-03-01',
    );
  });

  // L4 — recoCount = mentions hors citation (guestWork inclus). Sert au
  // libellé « Recommandée N fois », qui ne doit pas compter les citations.
  it('recoCount exclut les citations mais garde recos + guestWork', () => {
    const mentions = [
      mention('m1', 'i1'), // reco
      mention('m2', 'i1', { kind: 'citation' }), // citation
      mention('m3', 'i1', { guestWork: true }), // reco (œuvre d'invité)
    ];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    const w = idx.get('i1')!;
    expect(w.mentionCount).toBe(3); // total (timeline)
    expect(w.recoCount).toBe(2); // reco + guestWork, PAS la citation
  });

  it('recoCount = 0 quand l’œuvre n’est que citée', () => {
    const mentions = [
      mention('m1', 'i1', { kind: 'citation' }),
      mention('m2', 'i1', { kind: 'citation' }),
    ];
    const idx = buildWorkIndex({ sourceId: 'ubm', items, mentions, episodes });
    const w = idx.get('i1')!;
    expect(w.mentionCount).toBe(2);
    expect(w.recoCount).toBe(0);
  });
});

describe('similarByCreator', () => {
  it('renvoie les items du même créateur', () => {
    const cur = item('i1', { creator: 'Bong Joon-ho' });
    const others = [
      item('i2', { creator: 'Bong Joon-ho' }),
      item('i3', { creator: 'Wes Anderson' }),
      item('i4', { creator: 'BONG JOON-HO' }),
    ];
    const out = similarByCreator(cur, others);
    expect(out.map((o) => o.id).sort()).toEqual(['i2', 'i4']);
  });
  it('vide si pas de créateur', () => {
    expect(similarByCreator(item('i1'), [item('i2', { creator: 'X' })])).toEqual([]);
  });
});

describe('workExternalLinks', () => {
  it('génère un lien TMDB si externalIds.tmdb + tmdbType', () => {
    const it = item('i1', {
      externalIds: { tmdb: 12345, tmdbType: 'movie' },
    });
    const out = workExternalLinks(it);
    expect(out.find((l) => l.label === 'TMDB')?.url).toBe(
      'https://www.themoviedb.org/movie/12345',
    );
  });
  it('inclut customLinks avec priorité', () => {
    const it = item('i1', {
      customLinks: [{ label: 'Site officiel', url: 'https://example.org' }],
    });
    expect(workExternalLinks(it)[0].label).toBe('Site officiel');
  });
  it('marque watchProviders avec leur éthique', () => {
    const it = item('i1', {
      watchProviders: [
        { name: 'Netflix', url: 'https://netflix.com/x', ethics: 'neutral' },
        { name: 'Mubi', url: 'https://mubi.com/x', ethics: 'indie' },
      ],
    });
    const out = workExternalLinks(it);
    expect(out.find((l) => l.label === 'Mubi')?.ethics).toBe('indie');
  });
});

describe('youtubeDeepLink', () => {
  it('ajoute &t=Ns quand transcriptSource=youtube + timestamp valide', () => {
    const jm = {
      mention: mention('m', 'i', {
        sourceRef: {
          sourceId: 'ubm',
          episodeGuid: 'g',
          timestamp: '01:00:30',
          transcriptSource: 'youtube',
        },
      }),
      episode: { guid: 'g', title: 't', youtubeUrl: 'https://yt/?v=ABC' },
    };
    expect(youtubeDeepLink(jm)).toBe('https://yt/?v=ABC&t=3630s');
  });
  it("n'ajoute pas d'offset si transcriptSource=acast (cf. politique)", () => {
    const jm = {
      mention: mention('m', 'i', {
        sourceRef: {
          sourceId: 'ubm',
          episodeGuid: 'g',
          timestamp: '00:01:00',
          transcriptSource: 'acast',
        },
      }),
      episode: { guid: 'g', title: 't', youtubeUrl: 'https://yt/?v=ABC' },
    };
    expect(youtubeDeepLink(jm)).toBe('https://yt/?v=ABC');
  });
  it('renvoie null si pas de youtubeUrl', () => {
    const jm = {
      mention: mention('m', 'i'),
      episode: { guid: 'g', title: 't' },
    };
    expect(youtubeDeepLink(jm)).toBeNull();
  });
});
