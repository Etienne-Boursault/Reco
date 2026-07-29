/**
 * tests/episode/test_page_episode_cov.test.ts
 *
 * Page épisode `/[source]/episode/[guid]`
 * (`src/pages/[source]/episode/[guid].astro`).
 *
 * Deux surfaces :
 *  1. `getStaticPaths` — tri des épisodes (saison puis numéro), chaînage
 *     prev/next, rattachement des recos non-`discarded`, et le choix produit
 *     de générer TOUS les épisodes (même sans reco) ;
 *  2. le rendu — trois sections (recos spontanées / œuvres d'invité·es /
 *     citations), compteurs singulier-pluriel, miniature YouTube ou artwork
 *     Acast, flèches de navigation actives ou désactivées, JSON-LD
 *     PodcastEpisode + recos.
 *
 * Les props de rendu proviennent de `getStaticPaths` : les deux moitiés sont
 * testées ensemble et restent cohérentes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText, TEST_SITE } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import EpisodePage, { getStaticPaths } from '../../src/pages/[source]/episode/[guid].astro';

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

const SOURCE = {
  id: 'ubm',
  data: {
    id: 'ubm',
    title: 'Un Bon Moment',
    hosts: ['Adèle'],
    theme: { colors: { bg: '#101010', surface: '#181818', text: '#fff', muted: '#999', accent: '#ff5500' } },
  },
};

function seed(
  map: Partial<Record<'sources' | 'recos' | 'episodes', Entry[]>>,
): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

function episode(guid: string, over: Record<string, unknown> = {}, sourceId = 'ubm'): Entry {
  return {
    data: {
      guid,
      sourceId: { id: sourceId },
      title: `Épisode ${guid}`,
      description: `Résumé de ${guid}`,
      number: 1,
      date: new Date('2026-03-14T00:00:00Z'),
      ...over,
    },
  };
}

function reco(id: string, guid: string, over: Record<string, unknown> = {}, sourceId = 'ubm'): Entry {
  return {
    data: {
      id,
      title: `Reco ${id}`,
      types: ['film'],
      creator: 'Un Réal',
      sourceId: { id: sourceId },
      episodeGuid: guid,
      status: 'validated',
      kind: 'reco',
      ...over,
    },
  };
}

interface EpPath {
  params: { source: string; guid: string };
  props: Record<string, unknown>;
}

async function paths(): Promise<EpPath[]> {
  return (await getStaticPaths()) as unknown as EpPath[];
}

async function renderEpisode(guid: string): Promise<string> {
  const p = (await paths()).find((x) => x.params.guid === guid);
  if (!p) throw new Error(`aucune route générée pour l'épisode ${guid}`);
  return renderPage(EpisodePage, {
    params: p.params,
    props: p.props,
    path: `/${p.params.source}/episode/${guid}`,
  });
}

function jsonLdOf(html: string): Record<string, unknown>[] {
  const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  if (!m) return [];
  const parsed = JSON.parse(m[1]);
  return Array.isArray(parsed) ? parsed : [parsed];
}

beforeEach(() => {
  getCollection.mockReset();
});

// ---------------------------------------------------------------------------
// getStaticPaths
// ---------------------------------------------------------------------------
describe('page épisode — getStaticPaths', () => {
  it('génère TOUS les épisodes, y compris ceux sans aucune reco', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { number: 1 }), episode('g2', { number: 2 })],
      recos: [reco('r1', 'g1')],
    });

    const p = await paths();
    expect(p.map((x) => x.params.guid)).toEqual(['g1', 'g2']);
    expect((p[1].props.recos as unknown[])).toEqual([]);
  });

  it('trie par saison puis numéro et chaîne prev/next dans cet ordre', async () => {
    seed({
      sources: [SOURCE],
      episodes: [
        episode('s2e1', { season: 2, number: 1 }),
        episode('s1e2', { season: 1, number: 2 }),
        episode('s1e1', { season: 1, number: 1 }),
      ],
    });

    const p = await paths();
    expect(p.map((x) => x.params.guid)).toEqual(['s1e1', 's1e2', 's2e1']);
    expect(p[0].props.prevGuid).toBeNull();
    expect(p[0].props.nextGuid).toBe('s1e2');
    expect(p[1].props.prevGuid).toBe('s1e1');
    expect(p[2].props.nextGuid).toBeNull();
  });

  it('un épisode sans numéro est renvoyé en fin de liste', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('sans', { number: undefined }), episode('g1', { number: 3 })],
    });

    expect((await paths()).map((x) => x.params.guid)).toEqual(['g1', 'sans']);
  });

  it('n’attache que les recos non-`discarded` de la bonne source', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [
        reco('ok', 'g1'),
        reco('jetee', 'g1', { status: 'discarded' }),
        reco('ailleurs', 'g1', {}, 'autre-podcast'),
      ],
    });

    const p = await paths();
    const recos = p[0].props.recos as Array<{ id: string }>;
    expect(recos.map((r) => r.id)).toEqual(['ok']);
  });

  it('isole les épisodes par source', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1'), episode('gx', {}, 'autre-podcast')],
    });

    expect((await paths()).map((x) => x.params.guid)).toEqual(['g1']);
  });

  it('ne produit rien sans source', async () => {
    seed({ sources: [], episodes: [episode('g1')] });
    expect(await paths()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Rendu — sections et compteurs
// ---------------------------------------------------------------------------
describe('page épisode — sections de recos', () => {
  it('sépare recos spontanées, œuvres d’invité·es et citations', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [
        reco('spont', 'g1', { title: 'Spontanée' }),
        reco('guest', 'g1', { title: 'Invitée', guestWork: true }),
        reco('cit', 'g1', { title: 'Citée', kind: 'citation' }),
      ],
    });
    const text = visibleText(await renderEpisode('g1'));

    expect(text).toContain('Recommandations (1)');
    expect(text).toContain('Leurs œuvres (1)');
    expect(text).toContain('Mentionné dans l’épisode (1)');
    expect(text).toContain('Spontanée');
    expect(text).toContain('Invitée');
    expect(text).toContain('Citée');
  });

  it('les œuvres d’invité·es comptent dans le total de recommandations', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [reco('a', 'g1'), reco('b', 'g1', { guestWork: true })],
    });
    const text = visibleText(await renderEpisode('g1'));

    expect(text).toContain('2 recommandations');
    expect(text).toContain('dont 1 œuvre présentée dans l’épisode');
  });

  it('accorde le breakdown au pluriel au-delà d’une œuvre d’invité·e', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [
        reco('a', 'g1', { guestWork: true }),
        reco('b', 'g1', { guestWork: true }),
      ],
    });

    expect(visibleText(await renderEpisode('g1'))).toContain(
      'dont 2 œuvres présentées dans l’épisode',
    );
  });

  it('une seule reco → compteur au singulier, sans breakdown', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [reco('a', 'g1')],
    });
    const text = visibleText(await renderEpisode('g1'));

    expect(text).toContain('1 recommandation');
    expect(text).not.toContain('dont');
    expect(text).not.toContain('mention');
  });

  it('compteur de citations au singulier puis au pluriel', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [reco('c1', 'g1', { kind: 'citation' })],
    });
    expect(visibleText(await renderEpisode('g1'))).toContain('1 mention');

    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [
        reco('c1', 'g1', { kind: 'citation' }),
        reco('c2', 'g1', { kind: 'citation' }),
      ],
    });
    expect(visibleText(await renderEpisode('g1'))).toContain('2 mentions');
  });

  it('épisode sans aucune reco → message dédié, aucune section', async () => {
    seed({ sources: [SOURCE], episodes: [episode('g1')], recos: [] });
    const text = visibleText(await renderEpisode('g1'));

    expect(text).toContain('Aucune recommandation extraite de cet épisode pour le moment.');
    expect(text).not.toContain('Recommandations (');
    expect(text).not.toContain('Leurs œuvres (');
  });

  it('la section « Leurs œuvres » masque le badge ⭐ sur ses cartes', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [reco('guest', 'g1', { guestWork: true })],
    });
    const html = await renderEpisode('g1');

    expect(html).toContain('guestwork-section');
    // Le titre de section porte déjà l'info (N5) → pas de badge par carte.
    expect(html).not.toContain('guestwork-badge');
  });
});

// ---------------------------------------------------------------------------
// Rendu — en-tête, miniature, navigation
// ---------------------------------------------------------------------------
describe('page épisode — en-tête et navigation', () => {
  it('miniature YouTube dérivée de l’URL, dans un lien externe', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { youtubeUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' })],
      recos: [reco('a', 'g1')],
    });
    const html = await renderEpisode('g1');

    expect(html).toContain('https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg');
    expect(html).toContain('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"');
    expect(html).toContain('target="_blank"');
  });

  it('sans YouTube, replie sur l’artwork Acast (image simple, pas de lien)', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { imageUrl: 'https://acast.example/cover.jpg' })],
      recos: [reco('a', 'g1')],
    });
    const html = await renderEpisode('g1');

    expect(html).toContain('https://acast.example/cover.jpg');
    expect(html).not.toContain('i.ytimg.com');
    expect(html).not.toContain('class="play"');
  });

  it('sans YouTube ni artwork, aucune image n’est rendue', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [reco('a', 'g1')],
    });
    const html = await renderEpisode('g1');

    expect(html).not.toContain('class="thumb"');
    expect(html).not.toContain('i.ytimg.com');
  });

  it('une URL YouTube sans paramètre `v` ne produit pas de miniature', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { youtubeUrl: 'https://youtu.be/abc' })],
      recos: [reco('a', 'g1')],
    });
    const html = await renderEpisode('g1');

    expect(html).not.toContain('i.ytimg.com');
    // Le lien vers YouTube reste, lui, bien présent.
    expect(html).toContain('href="https://youtu.be/abc"');
  });

  it('flèches prev/next actives au milieu de la liste', async () => {
    seed({
      sources: [SOURCE],
      episodes: [
        episode('g1', { number: 1 }),
        episode('g2', { number: 2 }),
        episode('g3', { number: 3 }),
      ],
    });
    const html = await renderEpisode('g2');

    expect(html).toContain('href="/ubm/episode/g1"');
    expect(html).toContain('href="/ubm/episode/g3"');
    expect(html).not.toContain('ep-arrow ep-arrow-prev disabled');
  });

  it('flèches désactivées aux extrémités', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { number: 1 }), episode('g2', { number: 2 })],
    });

    const first = await renderEpisode('g1');
    expect(first).toContain('ep-arrow ep-arrow-prev disabled');
    expect(first).toContain('href="/ubm/episode/g2"');

    const last = await renderEpisode('g2');
    expect(last).toContain('ep-arrow ep-arrow-next disabled');
    expect(last).toContain('href="/ubm/episode/g1"');
  });

  it('libellé d’épisode « #N », ou « SxE·Ey » quand la saison est connue', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { number: 7 })],
    });
    expect(visibleText(await renderEpisode('g1'))).toContain('#7');

    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { season: 2, number: 7 })],
    });
    expect(visibleText(await renderEpisode('g1'))).toContain('S2·E7');
  });

  it('aucun libellé d’épisode quand ni saison ni numéro', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { number: undefined })],
    });

    expect(await renderEpisode('g1')).not.toContain('class="epnum"');
  });

  it('utilise le titre du flux (français), pas le titre YouTube', async () => {
    seed({
      sources: [SOURCE],
      episodes: [
        episode('g1', { title: 'Titre français', youtubeTitle: 'ENGLISH CLICKBAIT TITLE' }),
      ],
    });
    const html = await renderEpisode('g1');

    expect(html).toMatch(/<h1[^>]*>Titre français<\/h1>/);
    expect(html).not.toContain('ENGLISH CLICKBAIT TITLE');
  });
});

// ---------------------------------------------------------------------------
// Rendu — SEO
// ---------------------------------------------------------------------------
describe('page épisode — SEO', () => {
  it('JSON-LD : PodcastEpisode puis une entrée par recommandation', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1')],
      recos: [
        reco('a', 'g1'),
        reco('b', 'g1', { guestWork: true }),
        reco('c', 'g1', { kind: 'citation' }),
      ],
    });
    const blocks = jsonLdOf(await renderEpisode('g1'));

    expect(blocks[0]['@type']).toBe('PodcastEpisode');
    expect(blocks[0].url).toBe(`${TEST_SITE}/ubm/episode/g1`);
    // Les citations sont exclues du JSON-LD ; les œuvres d'invités non.
    expect(blocks).toHaveLength(3);
    expect(blocks.slice(1).map((b) => b.name)).toEqual(['Reco a', 'Reco b']);
  });

  it('un épisode sans date ne casse pas le JSON-LD', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { date: undefined })],
      recos: [reco('a', 'g1')],
    });
    const blocks = jsonLdOf(await renderEpisode('g1'));

    expect(blocks[0]['@type']).toBe('PodcastEpisode');
    expect(blocks[0].datePublished).toBeUndefined();
  });

  it('meta description accordée au nombre de recommandations', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { title: 'Mon épisode' })],
      recos: [reco('a', 'g1')],
    });
    expect(await renderEpisode('g1')).toContain(
      '<meta name="description" content="1 recommandation extraite de Mon épisode, épisode du podcast Un Bon Moment.">',
    );

    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { title: 'Mon épisode' })],
      recos: [reco('a', 'g1'), reco('b', 'g1')],
    });
    expect(await renderEpisode('g1')).toContain(
      '<meta name="description" content="2 recommandations extraites de Mon épisode, épisode du podcast Un Bon Moment.">',
    );
  });

  it('la miniature YouTube devient l’image OG (prioritaire sur la carte Satori)', async () => {
    seed({
      sources: [SOURCE],
      episodes: [episode('g1', { youtubeUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' })],
    });

    expect(await renderEpisode('g1')).toContain(
      '<meta property="og:image" content="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg">',
    );
  });

  it('sans miniature, l’image OG retombe sur la carte générée de l’épisode', async () => {
    seed({ sources: [SOURCE], episodes: [episode('g1')] });

    expect(await renderEpisode('g1')).toContain(
      `<meta property="og:image" content="${TEST_SITE}/og/ubm/episode/g1.png">`,
    );
  });
});
