/**
 * tests/stats/test_pages_stats_cov.test.ts
 *
 * Les deux pages statistiques :
 *  - `src/pages/stats.astro` — global, sidecar `tools/output/stats/_global/` ;
 *  - `src/pages/[source]/stats.astro` — par source, sidecar
 *    `tools/output/stats/<source>/`.
 *
 * Le cœur non-couvert par les tests de `src/lib/stats/**` est le
 * **chargement du sidecar** (R-P1-24) : présent et valide → on l'utilise tel
 * quel et on ne touche PAS aux collections ; absent ou corrompu → on retombe
 * sur le calcul depuis `getCollection`. On teste les trois cas en
 * interceptant `node:fs` de façon chirurgicale (seuls les chemins
 * `tools/output/stats/**` sont détournés — le reste garde le vrai `fs`, car
 * Astro et Vite lisent des fichiers pendant le rendu).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText, TEST_SITE } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

/** Contenu simulé des sidecars, indexé par nom de dossier (`_global`, …). */
const sidecars = new Map<string, string>();

function sidecarKey(path: string): string | null {
  const m = String(path).replace(/\\/g, '/').match(/tools\/output\/stats\/([^/]+)\/stats\.json$/);
  return m ? m[1] : null;
}

vi.mock('node:fs', async (importOriginal) => {
  const real = await importOriginal<typeof import('node:fs')>();
  return {
    ...real,
    default: real,
    existsSync: (p: Parameters<typeof real.existsSync>[0]) => {
      const key = sidecarKey(String(p));
      if (key !== null) return sidecars.has(key);
      return real.existsSync(p);
    },
    readFileSync: ((p: unknown, ...rest: unknown[]) => {
      const key = sidecarKey(String(p));
      if (key !== null && sidecars.has(key)) return sidecars.get(key)!;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return (real.readFileSync as any)(p, ...rest);
    }) as typeof real.readFileSync,
  };
});

import GlobalStats from '../../src/pages/stats.astro';
import SourceStats, { getStaticPaths } from '../../src/pages/[source]/stats.astro';

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
  map: Partial<Record<'sources' | 'episodes' | 'mentions' | 'items', Entry[]>>,
): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

/** Jeu de collections minimal : 1 source, 1 épisode, 1 œuvre, 2 mentions. */
function seedCollections(): void {
  seed({
    sources: [{ id: 'ubm', data: { id: 'ubm', hosts: ['Adèle'] } }],
    episodes: [{ data: { sourceId: { id: 'ubm' }, date: new Date('2026-03-14T00:00:00Z') } }],
    mentions: [
      { data: { itemId: 'w1', recommendedBy: 'Bruno', status: 'validated', sourceRef: { sourceId: 'ubm' } } },
      { data: { itemId: 'w1', recommendedBy: 'Adèle', status: 'validated', sourceRef: { sourceId: 'ubm' } } },
    ],
    items: [{ data: { id: 'w1', title: 'Parasite', types: ['film'] } }],
  });
}

/** Snapshot sidecar valide au regard de `statsSnapshotSchema`. */
function snapshot(over: Record<string, unknown> = {}): string {
  return JSON.stringify({
    schemaVersion: 1,
    generatedAt: '2026-07-01T12:00:00Z',
    global: {
      podcastsCount: 7,
      episodesCount: 70,
      recommendationsCount: 700,
      uniqueWorksCount: 500,
      uniqueGuestsCount: 42,
    },
    perSource: {},
    topGuests: [{ name: 'Sidecar Guest', slug: 'sidecar-guest', count: 9 }],
    topWorks: [{ id: 'sw1', title: 'Œuvre du sidecar', type: 'serie', mentionsCount: 5 }],
    typeDistribution: { film: 3, serie: 2 },
    monthlyEpisodes: [{ month: '2026-01', count: 4 }, { month: '2026-05', count: 6 }],
    ...over,
  });
}

function jsonLdOf(html: string): Record<string, unknown> {
  const m = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  return JSON.parse(m![1]) as Record<string, unknown>;
}

/** Collections demandées par la page (hors `sources`, lue par le footer). */
function heavyCollectionsLoaded(): string[] {
  return getCollection.mock.calls
    .map((c) => c[0] as string)
    .filter((n) => n !== 'sources');
}

beforeEach(() => {
  getCollection.mockReset();
  // `SiteFooter` (monté par Layout) lit toujours `sources` : le mock doit
  // répondre un tableau même quand le test ne sème rien.
  getCollection.mockImplementation(async () => []);
  sidecars.clear();
});

// ---------------------------------------------------------------------------
// /stats
// ---------------------------------------------------------------------------
describe('/stats — page globale', () => {
  const render = () => renderPage(GlobalStats, { path: '/stats' });

  it('est marquée prerender (page statique)', async () => {
    const mod = await import('../../src/pages/stats.astro');
    expect((mod as unknown as { prerender: boolean }).prerender).toBe(true);
  });

  it('sans sidecar, calcule le snapshot depuis les collections', async () => {
    seedCollections();
    const text = visibleText(await render());

    // 1 podcast, 1 épisode, 2 mentions, 1 œuvre, 1 invité (Adèle est hôte).
    expect(text).toContain('Parasite');
    expect(text).toContain('Bruno');
    expect(getCollection).toHaveBeenCalledWith('items');
  });

  it('avec sidecar valide, l’utilise et n’ouvre AUCUNE collection', async () => {
    sidecars.set('_global', snapshot());
    seedCollections();
    const text = visibleText(await render());

    expect(text).toContain('Œuvre du sidecar');
    expect(text).toContain('Sidecar Guest');
    // R-P1-24 : le sidecar court-circuite la lecture des collections lourdes.
    expect(heavyCollectionsLoaded()).toEqual([]);
  });

  it('sidecar illisible (JSON cassé) → repli silencieux sur le calcul', async () => {
    sidecars.set('_global', '{ pas du json');
    seedCollections();
    const text = visibleText(await render());

    expect(text).toContain('Parasite');
    expect(getCollection).toHaveBeenCalled();
  });

  it('sidecar hors-schéma (clé inconnue) → repli sur le calcul', async () => {
    sidecars.set('_global', snapshot({ cleInattendue: true }));
    seedCollections();
    const text = visibleText(await render());

    expect(text).toContain('Parasite');
    expect(text).not.toContain('Œuvre du sidecar');
  });

  it('traduit les types bruts en libellés humains (chart et sous-ligne)', async () => {
    sidecars.set('_global', snapshot());
    const text = visibleText(await render());

    // typeDistribution : `film` → « Films », `serie` → « Séries ».
    expect(text).toContain('Films');
    expect(text).toContain('Séries');
    // topWorks[].sub : `serie` → « Série » (singulier).
    expect(text).toContain('Série');
    expect(text).not.toMatch(/\bserie\b/);
  });

  it('un type inconnu du mapping est affiché tel quel (pas de trou)', async () => {
    sidecars.set(
      '_global',
      snapshot({
        typeDistribution: { ovni: 4 },
        topWorks: [{ id: 'x', title: 'Objet non identifié', type: 'ovni', mentionsCount: 2 }],
      }),
    );
    const text = visibleText(await render());

    expect(text).toContain('Objet non identifié');
    // Ni libellé pluriel ni libellé singulier connus → la clé brute est rendue.
    expect(text.match(/ovni/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it('affiche la date de génération formatée en français', async () => {
    sidecars.set('_global', snapshot());
    expect(visibleText(await render())).toContain('01 juillet 2026');
  });

  it('JSON-LD Dataset avec URL de page, distribution et couverture temporelle', async () => {
    sidecars.set('_global', snapshot());
    const schema = jsonLdOf(await render());

    expect(schema['@type']).toBe('Dataset');
    expect(schema.url).toBe(`${TEST_SITE}/stats`);
    expect(schema.temporalCoverage).toBe('2026-01/2026-05');
    expect(JSON.stringify(schema.distribution)).toContain(`${TEST_SITE}/stats.json`);
  });

  it('affiche les cinq compteurs globaux du snapshot', async () => {
    sidecars.set('_global', snapshot());
    const text = visibleText(await render());

    for (const n of ['7', '70', '700', '500', '42']) {
      expect(text).toContain(n);
    }
  });

  it('collections vides → page rendue avec les états vides', async () => {
    seed({ sources: [], episodes: [], mentions: [], items: [] });
    const text = visibleText(await render());

    expect(text).toContain('Statistiques');
    // Les listes top-N sont vides mais la page tient debout.
    expect(text).not.toContain('undefined');
  });

  it('tolère `hosts`, `date` et `recommendedBy` absents des collections', async () => {
    seed({
      sources: [{ id: 'ubm', data: { id: 'ubm' } }],
      episodes: [{ data: { sourceId: { id: 'ubm' } } }],
      mentions: [{ data: { itemId: 'w1', status: 'validated', sourceRef: { sourceId: 'ubm' } } }],
      items: [{ data: { id: 'w1', title: 'Sans hôte', types: ['livre'] } }],
    });
    const text = visibleText(await render());

    expect(text).toContain('Sans hôte');
  });
});

// ---------------------------------------------------------------------------
// /[source]/stats
// ---------------------------------------------------------------------------
describe('/[source]/stats — page par source', () => {
  const render = () =>
    renderPage(SourceStats, {
      params: { source: 'ubm' },
      props: { source: SOURCE },
      path: '/ubm/stats',
    });

  it('est marquée prerender', async () => {
    const mod = await import('../../src/pages/[source]/stats.astro');
    expect((mod as unknown as { prerender: boolean }).prerender).toBe(true);
  });

  it('getStaticPaths émet une page par source', async () => {
    seed({ sources: [SOURCE, { id: 'autre', data: { id: 'autre', title: 'Autre' } }] });
    const paths = (await getStaticPaths()) as Array<{ params: { source: string } }>;

    expect(paths.map((p) => p.params.source)).toEqual(['ubm', 'autre']);
  });

  it('lit le sidecar du dossier de LA source (pas `_global`)', async () => {
    sidecars.set('_global', snapshot({ topWorks: [{ id: 'g', title: 'Global only', type: 'film', mentionsCount: 1 }] }));
    sidecars.set('ubm', snapshot());
    seedCollections();
    const text = visibleText(await render());

    expect(text).toContain('Œuvre du sidecar');
    expect(text).not.toContain('Global only');
    expect(heavyCollectionsLoaded()).toEqual([]);
  });

  it('sans sidecar de source, calcule à partir des collections filtrées', async () => {
    seed({
      sources: [SOURCE],
      episodes: [
        { data: { sourceId: { id: 'ubm' }, date: new Date('2026-03-14T00:00:00Z') } },
        { data: { sourceId: { id: 'autre' }, date: new Date('2026-03-14T00:00:00Z') } },
      ],
      mentions: [
        { data: { itemId: 'w1', recommendedBy: 'Bruno', status: 'validated', sourceRef: { sourceId: 'ubm' } } },
        { data: { itemId: 'w2', recommendedBy: 'Carla', status: 'validated', sourceRef: { sourceId: 'autre' } } },
      ],
      items: [
        { data: { id: 'w1', title: 'Chez nous', types: ['film'] } },
        { data: { id: 'w2', title: 'Chez eux', types: ['film'] } },
      ],
    });
    const text = visibleText(await render());

    expect(text).toContain('Chez nous');
    expect(text).not.toContain('Chez eux');
    expect(text).toContain('Bruno');
    expect(text).not.toContain('Carla');
  });

  it('sidecar de source corrompu → repli sur le calcul', async () => {
    sidecars.set('ubm', '<<<pas du json>>>');
    seedCollections();
    const text = visibleText(await render());

    expect(text).toContain('Parasite');
    expect(getCollection).toHaveBeenCalled();
  });

  it('titre, thème et lien de retour sont ceux de la source', async () => {
    sidecars.set('ubm', snapshot());
    const html = await render();

    expect(html).toContain('<title>Statistiques publiques — Un Bon Moment — Reco</title>');
    expect(html).toContain('--accent:#ff5500');
    expect(html).toContain('href="/ubm"');
    expect(visibleText(html)).toContain('retour au podcast Un Bon Moment');
  });

  it('JSON-LD Dataset scopé sur l’URL de la source', async () => {
    sidecars.set('ubm', snapshot());
    const schema = jsonLdOf(await render());

    expect(schema['@type']).toBe('Dataset');
    expect(schema.url).toBe(`${TEST_SITE}/ubm/stats`);
    expect(schema.name).toBe('Statistiques publiques — Un Bon Moment');
  });

  it('un type inconnu du mapping est affiché tel quel', async () => {
    sidecars.set(
      'ubm',
      snapshot({
        typeDistribution: { ovni: 4 },
        topWorks: [{ id: 'x', title: 'Objet non identifié', type: 'ovni', mentionsCount: 2 }],
      }),
    );
    const text = visibleText(await render());

    expect(text).toContain('Objet non identifié');
    expect(text.match(/ovni/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it('tolère `date` et `recommendedBy` absents des collections', async () => {
    seed({
      sources: [SOURCE],
      episodes: [{ data: { sourceId: { id: 'ubm' } } }],
      mentions: [{ data: { itemId: 'w1', status: 'validated', sourceRef: { sourceId: 'ubm' } } }],
      items: [{ data: { id: 'w1', title: 'Parasite', types: ['film'] } }],
    });
    const text = visibleText(await render());

    expect(text).toContain('Parasite');
    // Sans `recommendedBy`, aucun invité n'est comptabilisé.
    expect(text).toContain('Statistiques publiques');
  });

  it('source sans `hosts` : le calcul ne casse pas', async () => {
    seed({
      sources: [{ id: 'ubm', data: { id: 'ubm', title: 'Un Bon Moment' } }],
      episodes: [],
      mentions: [{ data: { itemId: 'w1', recommendedBy: 'Bruno', status: 'validated', sourceRef: { sourceId: 'ubm' } } }],
      items: [{ data: { id: 'w1', title: 'Parasite', types: ['film'] } }],
    });
    const html = await renderPage(SourceStats, {
      params: { source: 'ubm' },
      props: { source: { id: 'ubm', data: { id: 'ubm', title: 'Un Bon Moment' } } },
      path: '/ubm/stats',
    });

    expect(visibleText(html)).toContain('Bruno');
  });
});
