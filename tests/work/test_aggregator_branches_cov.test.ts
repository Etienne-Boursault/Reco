/**
 * tests/work/test_aggregator_branches_cov.test.ts — Branches restantes de
 * `src/lib/work/aggregator.ts` : join d'épisode manquant, tri sans date,
 * garde XSS des URLs, externalIds (spotify / openlibrary / watchPage / tv)
 * et deep-link YouTube dégradé.
 */
import { describe, it, expect } from 'vitest';
import {
  buildWorkIndex,
  workExternalLinks,
  youtubeDeepLink,
  type EpisodeLike,
  type ItemLike,
  type MentionLike,
} from '../../src/lib/work/aggregator';

function item(id: string, over: Partial<ItemLike> = {}): ItemLike {
  return { id, title: id, types: ['film'], ...over };
}
function mention(id: string, itemId: string, over: Partial<MentionLike> = {}): MentionLike {
  return {
    id,
    itemId,
    sourceRef: { sourceId: 'ubm', episodeGuid: `ep-${id}` },
    kind: 'reco',
    status: 'validated',
    ...over,
  };
}

describe('buildWorkIndex — join épisode', () => {
  it("episodeGuid inconnu → épisode null (pas de crash)", () => {
    const idx = buildWorkIndex({
      sourceId: 'ubm',
      items: [item('i1')],
      mentions: [mention('m1', 'i1', { sourceRef: { sourceId: 'ubm', episodeGuid: 'absent' } })],
      episodes: [],
    });
    const agg = idx.get('i1')!;
    expect(agg.mentions[0].episode).toBeNull();
    expect(agg.lastMentionedAt).toBeNull();
  });

  it('episodeGuid absent (null) → épisode null', () => {
    const idx = buildWorkIndex({
      sourceId: 'ubm',
      items: [item('i1')],
      mentions: [mention('m1', 'i1', { sourceRef: { sourceId: 'ubm', episodeGuid: null } })],
      episodes: [{ guid: 'ep-m1', title: 'Ép' }],
    });
    expect(idx.get('i1')!.mentions[0].episode).toBeNull();
  });

  it('mentions sans date d épisode passent en queue du tri', () => {
    const episodes: EpisodeLike[] = [
      { guid: 'ep-m1', title: 'sans date' },
      { guid: 'ep-m2', title: 'avec date', date: new Date('2026-03-01') },
    ];
    const idx = buildWorkIndex({
      sourceId: 'ubm',
      items: [item('i1')],
      mentions: [mention('m1', 'i1'), mention('m2', 'i1')],
      episodes,
      now: new Date('2026-04-01'),
    });
    const agg = idx.get('i1')!;
    expect(agg.mentions.map((jm) => jm.mention.id)).toEqual(['m2', 'm1']);
    expect(agg.lastMentionedAt).toEqual(new Date('2026-03-01'));
    // Une seule mention datée dans la fenêtre ⇒ pas trending.
    expect(agg.trending).toBe(false);
  });

  it('aucune mention datée → lastMentionedAt null', () => {
    const idx = buildWorkIndex({
      sourceId: 'ubm',
      items: [item('i1')],
      mentions: [mention('m1', 'i1'), mention('m2', 'i1')],
      episodes: [
        { guid: 'ep-m1', title: 'a' },
        { guid: 'ep-m2', title: 'b' },
      ],
    });
    expect(idx.get('i1')!.lastMentionedAt).toBeNull();
  });
});

describe('workExternalLinks — garde XSS (isSafeHttpUrl)', () => {
  it('rejette un customLink `javascript:`', () => {
    const out = workExternalLinks(
      item('i1', { customLinks: [{ label: 'Piège', url: 'javascript:alert(1)' }] }),
    );
    expect(out).toEqual([]);
  });

  it('rejette un customLink vide et une url non-string', () => {
    const out = workExternalLinks(
      item('i1', {
        customLinks: [
          { label: 'Vide', url: '' },
          { label: 'Nombre', url: 42 as unknown as string },
        ],
      }),
    );
    expect(out).toEqual([]);
  });

  it("rejette une url http(s) syntaxiquement invalide (host vide)", () => {
    const out = workExternalLinks(
      item('i1', { customLinks: [{ label: 'Cassé', url: 'https://' }] }),
    );
    expect(out).toEqual([]);
  });

  it('rejette un watchProvider `data:`', () => {
    const out = workExternalLinks(
      item('i1', { watchProviders: [{ name: 'Piège', url: 'data:text/html,<script>' }] }),
    );
    expect(out).toEqual([]);
  });
});

describe('workExternalLinks — externalIds', () => {
  it('tmdbType `tv` → lien série TMDB', () => {
    const out = workExternalLinks(item('i1', { externalIds: { tmdb: 1399, tmdbType: 'tv' } }));
    expect(out).toEqual([{ label: 'TMDB', url: 'https://www.themoviedb.org/tv/1399' }]);
  });

  it('spotify → lien open.spotify.com', () => {
    const out = workExternalLinks(item('i1', { externalIds: { spotify: 'album/abc' } }));
    expect(out).toEqual([{ label: 'Spotify', url: 'https://open.spotify.com/album/abc' }]);
  });

  it('spotify chaîne vide → ignoré', () => {
    expect(workExternalLinks(item('i1', { externalIds: { spotify: '' } }))).toEqual([]);
  });

  it('openlibrary → lien marqué `indie`', () => {
    const out = workExternalLinks(item('i1', { externalIds: { openlibrary: 'OL1W' } }));
    expect(out).toEqual([
      { label: 'OpenLibrary', url: 'https://openlibrary.org/works/OL1W', ethics: 'indie' },
    ]);
  });

  it('openlibrary chaîne vide → ignoré', () => {
    expect(workExternalLinks(item('i1', { externalIds: { openlibrary: '' } }))).toEqual([]);
  });

  it('watchPage : url http(s) acceptée, url non-http rejetée', () => {
    expect(
      workExternalLinks(item('i1', { externalIds: { watchPage: 'https://themoviedb.org/x/watch' } })),
    ).toEqual([{ label: 'Où regarder', url: 'https://themoviedb.org/x/watch' }]);
    expect(
      workExternalLinks(item('i1', { externalIds: { watchPage: 'ftp://themoviedb.org/x' } })),
    ).toEqual([]);
  });

  it('watchPage non-string → ignoré', () => {
    expect(workExternalLinks(item('i1', { externalIds: { watchPage: 12 } }))).toEqual([]);
  });

  it('dédup par label insensible à la casse — customLinks prioritaires', () => {
    const out = workExternalLinks(
      item('i1', {
        customLinks: [
          { label: 'Spotify', url: 'https://custom.example/spotify' },
          { label: 'spotify', url: 'https://doublon.example' },
        ],
        externalIds: { spotify: 'album/abc' },
      }),
    );
    expect(out).toEqual([{ label: 'Spotify', url: 'https://custom.example/spotify' }]);
  });
});

describe('youtubeDeepLink — cas dégradés', () => {
  const base = {
    mention: {
      id: 'm1',
      itemId: 'i1',
      sourceRef: {
        sourceId: 'ubm',
        timestamp: '00:01:00',
        transcriptSource: 'youtube' as const,
      },
      kind: 'reco' as const,
      status: 'validated' as const,
    },
    episode: { guid: 'e1', title: 'Ép', youtubeUrl: 'https://youtu.be/abc' },
  };

  it('timestamp au mauvais format → url brute', () => {
    const url = youtubeDeepLink({
      ...base,
      mention: {
        ...base.mention,
        sourceRef: { ...base.mention.sourceRef, timestamp: '1:02' },
      },
    });
    expect(url).toBe('https://youtu.be/abc');
  });

  it('timestamp 00:00:00 → url brute (offset nul inutile)', () => {
    const url = youtubeDeepLink({
      ...base,
      mention: {
        ...base.mention,
        sourceRef: { ...base.mention.sourceRef, timestamp: '00:00:00' },
      },
    });
    expect(url).toBe('https://youtu.be/abc');
  });

  it('url sans query → suffixe `?t=Ns`', () => {
    expect(youtubeDeepLink(base)).toBe('https://youtu.be/abc?t=60s');
  });

  it('url avec query → suffixe `&t=Ns`', () => {
    const url = youtubeDeepLink({
      ...base,
      episode: { ...base.episode, youtubeUrl: 'https://www.youtube.com/watch?v=abc' },
    });
    expect(url).toBe('https://www.youtube.com/watch?v=abc&t=60s');
  });
});
