/**
 * tests/about/test_pages_about_manifeste_cov.test.ts
 *
 * Rendu unitaire (Astro Container API) des deux pages éditoriales
 * `src/pages/a-propos.astro` et `src/pages/manifeste.astro`.
 *
 * Complète `test_a_propos_route.test.ts`, qui lit `dist/` **après un build**
 * et se skippe donc en local : ici, aucune dépendance au build, et surtout
 * on couvre le frontmatter — compteurs du catalogue (exclusion des
 * `discarded` et des citations), JSON-LD WebPage + BreadcrumbList, et le
 * repli d'adresse de contact quand `siteConfig.contactEmail` n'est pas
 * renseigné.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText, TEST_SITE } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import About from '../../src/pages/a-propos.astro';
import Manifeste from '../../src/pages/manifeste.astro';

interface Entry {
  data: Record<string, unknown>;
}

function seed(
  map: Partial<Record<'sources' | 'recos' | 'episodes', Entry[]>>,
): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

function reco(id: string, over: Record<string, unknown> = {}): Entry {
  return {
    data: {
      id,
      title: `Reco ${id}`,
      types: ['film'],
      sourceId: { id: 'ubm' },
      episodeGuid: 'g1',
      status: 'validated',
      kind: 'reco',
      ...over,
    },
  };
}

function jsonLdOf(html: string): Record<string, unknown>[] {
  const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  const parsed = JSON.parse(m![1]);
  return Array.isArray(parsed) ? parsed : [parsed];
}

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockImplementation(async () => []);
});

describe('/a-propos', () => {
  const render = () => renderPage(About, { path: '/a-propos' });

  it('affiche le titre, la baseline et les sections attendues', async () => {
    const text = visibleText(await render());

    expect(text).toContain('À propos');
    expect(text).toContain('Catalogue à ce jour');
    expect(text).toContain('podcasts indexés');
    expect(text).toContain('épisodes');
    expect(text).toContain('recommandations');
  });

  it('compte les recos hors `discarded` et hors citations', async () => {
    seed({
      sources: [{ data: { id: 'ubm' } }, { data: { id: 'autre' } }],
      episodes: [{ data: { guid: 'g1' } }, { data: { guid: 'g2' } }, { data: { guid: 'g3' } }],
      recos: [
        reco('a'),
        reco('b'),
        reco('c', { status: 'discarded' }),
        reco('d', { kind: 'citation' }),
      ],
    });
    const text = visibleText(await render());

    expect(text).toContain('2 podcasts indexés');
    expect(text).toContain('3 épisodes');
    expect(text).toContain('2 recommandations');
  });

  it('accorde les compteurs au singulier sur un déploiement mono-source', async () => {
    seed({
      sources: [{ data: { id: 'ubm' } }],
      episodes: [{ data: { guid: 'g1' } }],
      recos: [reco('a')],
    });
    const text = visibleText(await render());

    expect(text).toContain('1 podcast indexé');
    expect(text).not.toContain('1 podcasts indexés');
    expect(text).toContain('1 épisode');
    expect(text).not.toContain('1 épisodes');
    expect(text).toContain('1 recommandation');
    expect(text).not.toContain('1 recommandations');
  });

  it('un catalogue vide affiche des zéros, pas des trous', async () => {
    const text = visibleText(await render());

    // En français, 0 prend le SINGULIER (cf. src/utils/plural.ts).
    expect(text).toContain('0 podcast indexé');
    expect(text).toContain('0 épisode');
    expect(text).toContain('0 recommandation');
    expect(text).not.toContain('0 podcasts indexés');
  });

  it('formate les grands nombres en locale FR', async () => {
    seed({
      recos: Array.from({ length: 3008 }, (_, i) => reco(`r${i}`)),
    });
    const html = await render();

    expect(html).toContain(`${(3008).toLocaleString('fr-FR')}</strong> recommandations`);
  });

  it('émet WebPage + BreadcrumbList en URLs absolues', async () => {
    const blocks = jsonLdOf(await render());

    expect(blocks.map((b) => b['@type'])).toEqual(['WebPage', 'BreadcrumbList']);
    expect(blocks[0].url).toBe(`${TEST_SITE}/a-propos`);
    expect((blocks[0].isPartOf as Record<string, unknown>).url).toBe(`${TEST_SITE}/`);

    const crumb = blocks[1] as { itemListElement: Array<{ item: string }> };
    expect(crumb.itemListElement.map((e) => e.item)).toEqual([
      `${TEST_SITE}/`,
      `${TEST_SITE}/a-propos`,
    ]);
  });

  it('renvoie vers le manifeste et le dépôt', async () => {
    const html = await render();

    expect(html).toContain('href="/manifeste"');
    expect(html).toContain('https://github.com/etiennebsl/Reco');
  });

  it('sans `contactEmail` configuré, replie sur l’adresse par défaut', async () => {
    expect(await render()).toContain('mailto:contact@source-internet.fr');
  });
});

describe('/a-propos — adresse de contact personnalisée', () => {
  it('utilise `siteConfig.contactEmail` quand il est renseigné', async () => {
    vi.resetModules();
    vi.doMock('../../src/config/site', () => ({
      siteConfig: {
        siteName: 'Reco',
        baseline: 'Catalogue de recommandations de podcasts',
        contactEmail: 'hello@exemple.fr',
      },
    }));
    const { default: AboutFork } = await import('../../src/pages/a-propos.astro');
    const html = await renderPage(AboutFork, { path: '/a-propos' });

    expect(html).toContain('mailto:hello@exemple.fr');
    expect(html).not.toContain('mailto:contact@source-internet.fr');

    vi.doUnmock('../../src/config/site');
    vi.resetModules();
  });
});

describe('/manifeste', () => {
  const render = () => renderPage(Manifeste, { path: '/manifeste' });

  it('rend le sommaire avec une ancre par section', async () => {
    const html = await render();

    for (const id of [
      'preambule',
      'anti-bollore',
      'libraries',
      'privacy',
      'opensource',
      'a11y',
      'selfhost',
      'transparency',
    ]) {
      expect(html).toContain(`href="#${id}"`);
      expect(html).toContain(`id="${id}"`);
    }
  });

  it('émet WebPage + BreadcrumbList sur l’URL du manifeste', async () => {
    const blocks = jsonLdOf(await render());

    expect(blocks.map((b) => b['@type'])).toEqual(['WebPage', 'BreadcrumbList']);
    expect(blocks[0].url).toBe(`${TEST_SITE}/manifeste`);

    const crumb = blocks[1] as { itemListElement: Array<{ item: string }> };
    expect(crumb.itemListElement[1].item).toBe(`${TEST_SITE}/manifeste`);
  });

  it('ne lit aucune collection (page purement éditoriale)', async () => {
    await render();

    // Seul le footer du Layout consulte `sources`.
    const asked = getCollection.mock.calls.map((c) => c[0]);
    expect(asked.filter((n) => n !== 'sources')).toEqual([]);
  });

  it('porte les positions éditoriales clés (Bolloré, Amazon, RGPD)', async () => {
    const text = visibleText(await render());

    expect(text).toContain('Bolloré');
    expect(text).toContain('Amazon');
    expect(text).toContain('Reco');
  });
});
