/**
 * tests/gallery/test_page_home_cov.test.ts
 *
 * Les deux pages « catalogue » :
 *  - `src/pages/index.astro` — racine. Deux modes : mono-source (le catalogue
 *    du seul podcast EST la home) et multi-source (liste de podcasts avec
 *    compteurs recos / épisodes / ⭐ confirmées) ;
 *  - `src/pages/[source]/index.astro` — index d'une source, qui **redirige**
 *    en 301 vers `/` quand le déploiement est mono-source (contenu dupliqué).
 *
 * La logique testée ici est celle des compteurs de la home : exclusion des
 * `discarded` et des `citation`, seuil « ⭐ confirmée » à 2 extracteurs,
 * décompte d'épisodes distincts par source.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, renderPageResponse, visibleText, TEST_SITE } from './_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import Home from '../../src/pages/index.astro';
import SourceIndex, { getStaticPaths } from '../../src/pages/[source]/index.astro';

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

function seed(
  map: Partial<Record<'sources' | 'recos' | 'episodes' | 'items' | 'mentions', Entry[]>>,
): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

function source(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    data: {
      id,
      title: `Podcast ${id}`,
      hosts: ['Adèle', 'Bruno'],
      tagline: `La tagline de ${id}`,
      ...over,
    },
  };
}

function reco(id: string, sourceId: string, guid: string, over: Record<string, unknown> = {}) {
  return {
    data: {
      id,
      title: `Reco ${id}`,
      types: ['film'],
      sourceId: { id: sourceId },
      episodeGuid: guid,
      status: 'validated',
      kind: 'reco',
      ...over,
    },
  };
}

function episode(guid: string, sourceId: string, over: Record<string, unknown> = {}) {
  return {
    data: {
      guid,
      sourceId: { id: sourceId },
      title: `Épisode ${guid}`,
      date: new Date('2026-03-14T00:00:00Z'),
      number: 1,
      ...over,
    },
  };
}

beforeEach(() => {
  getCollection.mockReset();
});

// ---------------------------------------------------------------------------
// / — mode multi-source (liste de podcasts)
// ---------------------------------------------------------------------------
describe('/ — annuaire multi-source', () => {
  function renderHome(): Promise<string> {
    return renderPage(Home, { path: '/' });
  }

  it('liste une carte par source, avec titre, tagline et animateurs', async () => {
    seed({
      sources: [source('ubm'), source('autre')],
      recos: [reco('r1', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const html = await renderHome();
    const text = visibleText(html);

    expect(html).toContain('href="/ubm"');
    expect(html).toContain('href="/autre"');
    expect(text).toContain('Podcast ubm');
    expect(text).toContain('La tagline de ubm');
    expect(text).toContain('par Adèle & Bruno');
  });

  it('affiche le h1 d’accueil (et pas le catalogue d’une source)', async () => {
    seed({ sources: [source('ubm'), source('autre')] });
    const text = visibleText(await renderHome());

    expect(text).toContain('Tout ce que vos podcasts vous ont conseillé.');
    expect(text).toContain('Le catalogue des recos');
  });

  it('compte les recos par source, hors `discarded` et hors citations', async () => {
    seed({
      sources: [source('ubm'), source('autre')],
      recos: [
        reco('r1', 'ubm', 'g1'),
        reco('r2', 'ubm', 'g1', { status: 'discarded' }),
        reco('r3', 'ubm', 'g1', { kind: 'citation' }),
        reco('r4', 'ubm', 'g2'),
      ],
      episodes: [episode('g1', 'ubm'), episode('g2', 'ubm')],
    });
    const text = visibleText(await renderHome());

    // 4 recos brutes → 2 comptées (1 discarded + 1 citation écartées).
    expect(text).toContain('2 recos');
    // Deux guids distincts porteurs d'une reco visible.
    expect(text).toContain('2 épisodes');
  });

  it('deux recos du même épisode ne comptent qu’un épisode', async () => {
    seed({
      sources: [source('ubm'), source('autre')],
      recos: [reco('r1', 'ubm', 'g1'), reco('r2', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const text = visibleText(await renderHome());

    expect(text).toContain('2 recos');
    expect(text).toContain('1 épisode');
  });

  it('badge ⭐ « confirmées » à partir de 2 extracteurs, pas avant', async () => {
    seed({
      sources: [source('ubm'), source('autre')],
      recos: [
        reco('r1', 'ubm', 'g1', { extractors: ['a', 'b'] }),
        reco('r2', 'ubm', 'g1', { extractors: ['a'] }),
        reco('r3', 'ubm', 'g1'), // pas de champ extractors du tout
      ],
      episodes: [episode('g1', 'ubm')],
    });
    const html = await renderHome();

    expect(visibleText(html)).toContain('1 confirmée');
    // Le détail « 2 LLMs » vit dans un aria-label (invisible au détagage).
    // Il est accordé lui aussi : le nom accessible ne doit pas dire
    // « 1 recommandations » à un lecteur d'écran.
    expect(html).toContain('1 recommandation confirmée par 2 LLMs indépendants');
    expect(html).not.toContain('1 recommandations');
  });

  it('aucune ⭐ affichée quand aucune reco n’atteint 2 extracteurs', async () => {
    seed({
      sources: [source('ubm'), source('autre')],
      recos: [reco('r1', 'ubm', 'g1', { extractors: ['a'] })],
      episodes: [episode('g1', 'ubm')],
    });
    const text = visibleText(await renderHome());

    expect(text).not.toContain('confirmées');
  });

  it('une source sans aucune reco affiche 0 reco / 0 épisode', async () => {
    seed({
      sources: [source('ubm'), source('vide')],
      recos: [reco('r1', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const text = visibleText(await renderHome());

    expect(text).toContain('0 reco');
    expect(text).toContain('0 épisode');
  });

  it('source sans tagline ni animateur : les blocs optionnels disparaissent', async () => {
    seed({
      sources: [
        source('nu', { tagline: undefined, hosts: [] }),
        source('autre'),
      ],
      recos: [],
      episodes: [],
    });
    const text = visibleText(await renderHome());

    expect(text).toContain('Podcast nu');
    expect(text).not.toContain('La tagline de nu');
    // Seul « autre » garde la ligne d'animateurs.
    expect(text.match(/par Adèle & Bruno/g)).toHaveLength(1);
  });

  it('formate les grands nombres en locale FR (séparateur de milliers)', async () => {
    const many = Array.from({ length: 1200 }, (_, i) => reco(`r${i}`, 'ubm', 'g1'));
    seed({
      sources: [source('ubm'), source('autre')],
      recos: many,
      episodes: [episode('g1', 'ubm')],
    });
    const html = await renderHome();

    // `fmt()` = toLocaleString('fr-FR') → séparateur de milliers, pas « 1200 ».
    expect(html).toContain(`${(1200).toLocaleString('fr-FR')} recos`);
    expect(html).not.toContain('>1200 recos');
  });

  it('émet le JSON-LD WebSite avec l’URL absolue de la racine', async () => {
    seed({ sources: [source('ubm'), source('autre')] });
    const html = await renderHome();
    const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
    const schema = JSON.parse(m![1]) as Record<string, unknown>;

    expect(schema['@type']).toBe('WebSite');
    expect(schema.url).toBe(`${TEST_SITE}/`);
    expect(schema.name).toBe('Reco');
    expect(schema.description).toBe('Catalogue de recommandations de podcasts');
  });
});

// ---------------------------------------------------------------------------
// / — mode mono-source (le catalogue du podcast EST la home)
// ---------------------------------------------------------------------------
describe('/ — mode mono-source', () => {
  it('rend le catalogue de l’unique source au lieu de l’annuaire', async () => {
    seed({
      sources: [source('ubm')],
      recos: [reco('r1', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const html = await renderPage(Home, { path: '/' });
    const text = visibleText(html);

    expect(text).toContain('Podcast ubm');
    // L'accroche de l'annuaire n'est pas rendue…
    expect(text).not.toContain('Tout ce que vos podcasts vous ont conseillé.');
    // …et le catalogue masque son lien « retour accueil » (isHome).
    expect(text).not.toContain('retour à l’accueil');
  });

  it('le JSON-LD du mode mono-source est le PodcastSeries, sans fil d’Ariane', async () => {
    seed({
      sources: [source('ubm')],
      recos: [reco('r1', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const html = await renderPage(Home, { path: '/' });
    const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
    const blocks = JSON.parse(m![1]) as Record<string, unknown>[];

    expect(blocks.map((b) => b['@type'])).toEqual(['PodcastSeries']);
  });
});

// ---------------------------------------------------------------------------
// /[source] — index de source
// ---------------------------------------------------------------------------
describe('/[source] — index de source', () => {
  it('getStaticPaths émet une route par source', async () => {
    seed({ sources: [source('ubm'), source('autre')] });
    const paths = (await getStaticPaths()) as Array<{ params: { source: string } }>;

    expect(paths.map((p) => p.params.source)).toEqual(['ubm', 'autre']);
  });

  it('redirige 301 vers / quand le déploiement est mono-source', async () => {
    seed({
      sources: [source('ubm')],
      recos: [reco('r1', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const res = await renderPageResponse(SourceIndex, {
      params: { source: 'ubm' },
      props: { source: source('ubm') },
      path: '/ubm',
    });

    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('/');
  });

  it('rend le catalogue (200) dès qu’il y a ≥2 sources', async () => {
    seed({
      sources: [source('ubm'), source('autre')],
      recos: [reco('r1', 'ubm', 'g1')],
      episodes: [episode('g1', 'ubm')],
    });
    const html = await renderPage(SourceIndex, {
      params: { source: 'ubm' },
      props: { source: source('ubm') },
      path: '/ubm',
    });

    expect(visibleText(html)).toContain('Podcast ubm');
    // Hors mode home : le lien de retour vers l'accueil est présent.
    expect(html).toContain('class="back"');
  });
});
