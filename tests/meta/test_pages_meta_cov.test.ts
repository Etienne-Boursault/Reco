/**
 * tests/meta/test_pages_meta_cov.test.ts
 *
 * Pages du méta-site (`source-internet.fr`) :
 *  - `src/pages/meta/[...all].astro` — annuaire (route catch-all) ;
 *  - `src/pages/meta/podcast/[slug].astro` — fiche d'un podcast indexé.
 *
 * Point clé (F-CRIT-1) : sur un fork standard, `loadMetaIndex()` renvoie
 * `null` et `getStaticPaths` doit rendre un tableau **vide** — Astro n'émet
 * alors aucun fichier, plutôt qu'une page 404 indexable. On mocke le loader
 * pour piloter les deux régimes sans dépendre de `META_MODE` ni du fichier
 * `tools/output/meta/meta_index.json`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

const loadMetaIndex = vi.fn();
vi.mock('../../src/lib/registry/meta-loader', () => ({
  loadMetaIndex: () => loadMetaIndex(),
}));

import MetaHome, { getStaticPaths as homePaths } from '../../src/pages/meta/[...all].astro';
import MetaPodcast, { getStaticPaths as podcastPaths } from '../../src/pages/meta/podcast/[slug].astro';

/** Fabrique une entrée de méta-index conforme à `RegistryEntry`. */
function entry(
  slug: string,
  over: {
    title?: string;
    tagline?: string;
    hosts?: string[];
    rssUrl?: string;
    manifesto?: string;
    mentionsCount?: number;
    lastUpdatedAt?: string;
  } = {},
) {
  return {
    sourceUrl: `https://${slug}.fr/reco-registry.json`,
    slug,
    registry: {
      schemaVersion: 1,
      siteUrl: `https://${slug}.fr`,
      podcast: {
        title: over.title ?? `Podcast ${slug}`,
        ...(over.tagline !== undefined ? { tagline: over.tagline } : {}),
        ...(over.rssUrl !== undefined ? { rssUrl: over.rssUrl } : {}),
        hosts: over.hosts ?? [],
        language: 'fr',
      },
      stats: {
        itemsCount: 10,
        mentionsCount: over.mentionsCount ?? 20,
        episodesCount: 30,
        guestsCount: 40,
        lastUpdatedAt: over.lastUpdatedAt ?? '2026-07-01T12:00:00Z',
      },
      meta: {
        generator: 'reco',
        generatedAt: '2026-07-01T12:00:00Z',
        ...(over.manifesto !== undefined ? { manifesto: over.manifesto } : {}),
      },
      endpoints: {},
    },
  };
}

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockImplementation(async () => []);
  loadMetaIndex.mockReset();
  loadMetaIndex.mockReturnValue(null);
});

// ---------------------------------------------------------------------------
// /meta/ — annuaire
// ---------------------------------------------------------------------------
describe('/meta/ — annuaire', () => {
  async function render(entries: ReturnType<typeof entry>[]): Promise<string> {
    loadMetaIndex.mockReturnValue({ entries });
    const p = (await homePaths()) as Array<{ params: unknown; props: Record<string, unknown> }>;
    return renderPage(MetaHome, { props: p[0].props, path: '/meta/' });
  }

  it('est marquée prerender', async () => {
    const mod = await import('../../src/pages/meta/[...all].astro');
    expect((mod as unknown as { prerender: boolean }).prerender).toBe(true);
  });

  it('F-CRIT-1 : aucun chemin généré quand le méta-index est absent', async () => {
    expect(await homePaths()).toEqual([]);
  });

  it('génère la route racine `/meta/` (segment catch-all vide)', async () => {
    loadMetaIndex.mockReturnValue({ entries: [entry('a')] });
    const p = (await homePaths()) as Array<{ params: { all?: string } }>;

    expect(p).toHaveLength(1);
    expect(p[0].params.all).toBeUndefined();
  });

  it('trie les entrées par nombre de mentions décroissant', async () => {
    loadMetaIndex.mockReturnValue({
      entries: [entry('petit', { mentionsCount: 5 }), entry('gros', { mentionsCount: 500 })],
    });
    const p = (await homePaths()) as Array<{ props: { entries: Array<{ slug: string }> } }>;

    expect(p[0].props.entries.map((e) => e.slug)).toEqual(['gros', 'petit']);
  });

  it('affiche une carte par podcast, liée à sa fiche interne', async () => {
    const html = await render([entry('alpha', { title: 'Alpha FM' }), entry('beta')]);

    expect(html).toContain('href="/meta/podcast/alpha"');
    expect(html).toContain('href="/meta/podcast/beta"');
    expect(visibleText(html)).toContain('Alpha FM');
  });

  it('compteur au singulier pour un seul podcast', async () => {
    expect(visibleText(await render([entry('alpha')]))).toContain('1 podcast indexé');
  });

  it('compteur au pluriel dès deux podcasts', async () => {
    const text = visibleText(await render([entry('a'), entry('b')]));
    expect(text).toContain('2 podcasts indexés');
  });

  it('méta-index vide → message d’attente, pas de grille', async () => {
    const html = await render([]);

    expect(html).toContain('meta-home__empty');
    expect(html).not.toContain('meta-home__grid');
    // Règle du projet (`src/utils/plural.ts`) : pluriel dès n >= 2, donc 0 et
    // 1 prennent le SINGULIER. Cette assertion exigeait « 0 podcasts indexés »
    // — elle gravait la seule violation du seuil dans tout le dépôt, et
    // contredisait frontalement `tests/about/…` qui assertait l'inverse sur
    // la même phrase.
    expect(visibleText(html)).toContain('0 podcast indexé');
    expect(visibleText(html)).not.toContain('0 podcasts indexés');
  });
});

// ---------------------------------------------------------------------------
// /meta/podcast/[slug] — fiche
// ---------------------------------------------------------------------------
describe('/meta/podcast/[slug] — fiche podcast', () => {
  async function render(e: ReturnType<typeof entry>): Promise<string> {
    loadMetaIndex.mockReturnValue({ entries: [e] });
    const p = (await podcastPaths()) as Array<{ params: { slug: string }; props: Record<string, unknown> }>;
    return renderPage(MetaPodcast, {
      params: p[0].params,
      props: p[0].props,
      path: `/meta/podcast/${p[0].params.slug}`,
    });
  }

  it('est marquée prerender', async () => {
    const mod = await import('../../src/pages/meta/podcast/[slug].astro');
    expect((mod as unknown as { prerender: boolean }).prerender).toBe(true);
  });

  it('F-CRIT-1 : aucun chemin sans méta-index', async () => {
    expect(await podcastPaths()).toEqual([]);
  });

  it('une route par entrée, indexée par slug', async () => {
    loadMetaIndex.mockReturnValue({ entries: [entry('alpha'), entry('beta')] });
    const p = (await podcastPaths()) as Array<{ params: { slug: string } }>;

    expect(p.map((x) => x.params.slug)).toEqual(['alpha', 'beta']);
  });

  it('affiche titre, stats et CTA externe vers le site du fork', async () => {
    const html = await render(entry('alpha', { title: 'Alpha FM' }));
    const text = visibleText(html);

    expect(html).toMatch(/<h1[^>]*>Alpha FM<\/h1>/);
    expect(text).toContain('10 œuvres référencées');
    expect(text).toContain('20 mentions');
    expect(text).toContain('30 épisodes');
    expect(text).toContain('40 invité·es');
    expect(html).toContain('href="https://alpha.fr"');
    expect(html).toContain('rel="noopener noreferrer external"');
    expect(html).toContain('href="/meta/"');
  });

  it('champs optionnels présents : tagline, hôtes, RSS, manifeste', async () => {
    const html = await render(
      entry('alpha', {
        tagline: 'Le meilleur podcast',
        hosts: ['Adèle', 'Bruno'],
        rssUrl: 'https://alpha.fr/rss.xml',
        manifesto: 'https://alpha.fr/manifeste',
      }),
    );
    const text = visibleText(html);

    expect(text).toContain('Le meilleur podcast');
    expect(text).toContain('Adèle · Bruno');
    expect(html).toContain('https://alpha.fr/rss.xml');
    expect(html).toContain('https://alpha.fr/manifeste');
  });

  it('champs optionnels absents : aucune ligne vide dans la fiche', async () => {
    const html = await render(entry('alpha'));
    const text = visibleText(html);

    expect(text).not.toContain('Animation');
    expect(text).not.toContain('Flux RSS');
    expect(text).not.toContain('Manifeste du fork');
    expect(html).not.toContain('class="lead"');
  });

  it('date de mise à jour formatée en français', async () => {
    const html = await render(entry('alpha', { lastUpdatedAt: '2026-07-01T12:00:00Z' }));

    expect(html).toContain('datetime="2026-07-01T12:00:00Z"');
    expect(visibleText(html)).toContain('1 juil. 2026');
  });

  it('date illisible : affichée telle quelle plutôt que « Invalid Date »', async () => {
    const html = await render(entry('alpha', { lastUpdatedAt: 'pas-une-date' }));

    expect(visibleText(html)).toContain('pas-une-date');
    expect(visibleText(html)).not.toContain('Invalid Date');
  });

  it('JSON-LD PodcastSeries avec les champs optionnels quand ils existent', async () => {
    const html = await render(
      entry('alpha', {
        title: 'Alpha FM',
        tagline: 'Le meilleur podcast',
        hosts: ['Adèle'],
        rssUrl: 'https://alpha.fr/rss.xml',
      }),
    );
    const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
    const schema = JSON.parse(m![1]) as Record<string, unknown>;

    expect(schema['@type']).toBe('PodcastSeries');
    expect(schema.name).toBe('Alpha FM');
    expect(schema.url).toBe('https://alpha.fr');
    expect(schema.description).toBe('Le meilleur podcast');
    expect(schema.webFeed).toBe('https://alpha.fr/rss.xml');
    expect(schema.inLanguage).toBe('fr');
    expect(schema.author).toEqual([{ '@type': 'Person', name: 'Adèle' }]);
  });

  it('JSON-LD sans description / webFeed / author quand les champs manquent', async () => {
    const html = await render(entry('alpha'));
    const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
    const schema = JSON.parse(m![1]) as Record<string, unknown>;

    expect(schema).not.toHaveProperty('description');
    expect(schema).not.toHaveProperty('webFeed');
    expect(schema).not.toHaveProperty('author');
  });

  it('sans tagline, la meta description retombe sur le sous-titre du méta-site', async () => {
    const html = await render(entry('alpha'));

    expect(html).toMatch(/<meta name="description" content="[^"]+">/);
    expect(html).not.toContain('content="undefined"');
  });
});
