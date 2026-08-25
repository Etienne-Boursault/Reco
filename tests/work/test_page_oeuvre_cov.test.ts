/**
 * tests/work/test_page_oeuvre_cov.test.ts
 *
 * Page œuvre `/[source]/oeuvre/[itemId]`
 * (`src/pages/[source]/oeuvre/[itemId].astro`).
 *
 * La page a deux surfaces bien distinctes :
 *  1. `getStaticPaths` — projection des collections vers `buildWorkIndex` :
 *     isolation par source (préfixe de dossier sur `entry.id`), dédoublonnage
 *     par `item.id`, et toute la batterie de `?? null` sur les champs
 *     optionnels ;
 *  2. le frontmatter de rendu — libellé de compteur (reco vs mention,
 *     singulier vs pluriel), emojis de type, handles sociaux, liens externes,
 *     JSON-LD typé, titre et meta description.
 *
 * Les props de rendu sont **celles produites par `getStaticPaths`** : on
 * n'invente pas de `WorkAggregate` à la main, ce qui garantit que les deux
 * moitiés restent cohérentes.
 *
 * `astro:content` est mocké — aucune lecture des collections réelles.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText, TEST_SITE } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import WorkPage, { getStaticPaths } from '../../src/pages/[source]/oeuvre/[itemId].astro';

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
  map: Partial<Record<'sources' | 'items' | 'mentions' | 'episodes', Entry[]>>,
): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

/** Entrée de collection `items` : `entry.id` = `<source>/<slug>`. */
function item(id: string, over: Record<string, unknown> = {}, sourceId = 'ubm'): Entry {
  return {
    id: `${sourceId}/${id}`,
    data: { id, title: `Titre ${id}`, types: ['film'], ...over },
  };
}

function mention(
  id: string,
  itemId: string,
  over: Record<string, unknown> = {},
  sourceId = 'ubm',
): Entry {
  return {
    data: {
      id,
      itemId,
      sourceRef: { sourceId, episodeGuid: 'g1' },
      kind: 'reco',
      status: 'validated',
      ...over,
    },
  };
}

function episode(guid: string, over: Record<string, unknown> = {}, sourceId = 'ubm'): Entry {
  return {
    data: {
      guid,
      sourceId: { id: sourceId },
      title: `Épisode ${guid}`,
      number: 42,
      // Date récente : `isTrending` regarde les 12 derniers mois.
      date: new Date(Date.now() - 30 * 24 * 3600 * 1000),
      ...over,
    },
  };
}

interface WorkPath {
  params: { source: string; itemId: string };
  props: Record<string, unknown>;
}

async function paths(): Promise<WorkPath[]> {
  return (await getStaticPaths()) as unknown as WorkPath[];
}

/** Rend la page œuvre `itemId` à partir des props réelles de getStaticPaths. */
async function renderWork(itemId: string): Promise<string> {
  const p = (await paths()).find((x) => x.params.itemId === itemId);
  if (!p) throw new Error(`aucune route générée pour l'item ${itemId}`);
  return renderPage(WorkPage, {
    params: p.params,
    props: p.props,
    path: `/${p.params.source}/oeuvre/${itemId}`,
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
describe('page œuvre — getStaticPaths', () => {
  it('émet une route par œuvre mentionnée, préfixée par la source', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1'), item('w2')],
      mentions: [mention('m1', 'w1'), mention('m2', 'w2')],
      episodes: [episode('g1')],
    });

    const p = await paths();
    expect(p.map((x) => x.params)).toEqual([
      { source: 'ubm', itemId: 'w1' },
      { source: 'ubm', itemId: 'w2' },
    ]);
  });

  it('n’émet PAS de route pour un item sans aucune mention visible', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1'), item('orphelin')],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });

    const p = await paths();
    expect(p.map((x) => x.params.itemId)).toEqual(['w1']);
  });

  it('une mention `discarded` ne suffit pas à créer la route', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1', { status: 'discarded' })],
      episodes: [episode('g1')],
    });

    expect(await paths()).toEqual([]);
  });

  it('isole les items par dossier source (`entry.id` préfixé)', async () => {
    seed({
      sources: [SOURCE],
      // Même itemId côté data, mais rangé sous une autre source.
      items: [item('w1'), item('w9', {}, 'autre-podcast')],
      mentions: [mention('m1', 'w1'), mention('m2', 'w9')],
      episodes: [episode('g1')],
    });

    const p = await paths();
    expect(p.map((x) => x.params.itemId)).toEqual(['w1']);
  });

  it('ignore les mentions rattachées à une autre source', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1'), item('w2')],
      mentions: [mention('m1', 'w1'), mention('m2', 'w2', {}, 'autre-podcast')],
      episodes: [episode('g1')],
    });

    const p = await paths();
    expect(p.map((x) => x.params.itemId)).toEqual(['w1']);
  });

  it('déduplique deux entrées portant le même `item.id`', async () => {
    seed({
      sources: [SOURCE],
      items: [
        { id: 'ubm/a', data: { id: 'w1', title: 'Première', types: ['film'] } },
        { id: 'ubm/b', data: { id: 'w1', title: 'Doublon', types: ['film'] } },
      ],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });

    const p = await paths();
    expect(p).toHaveLength(1);
    // La dernière entrée écrase la première dans la Map de dédup.
    expect((p[0].props.work as { item: { title: string } }).item.title).toBe('Doublon');
  });

  it('normalise les champs optionnels absents en `null` / valeurs vides', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')], // ni creator, ni year, ni externalIds, ni liens
      mentions: [
        { data: { id: 'm1', itemId: 'w1', sourceRef: { sourceId: 'ubm' }, kind: 'reco', status: 'validated' } },
      ],
      episodes: [],
    });

    const p = await paths();
    const work = p[0].props.work as {
      item: Record<string, unknown>;
      mentions: Array<{ mention: Record<string, unknown>; episode: unknown }>;
    };
    expect(work.item.creator).toBeNull();
    expect(work.item.year).toBeNull();
    expect(work.item.externalIds).toEqual({});
    expect(work.item.customLinks).toEqual([]);
    expect(work.item.watchProviders).toEqual([]);

    const m = work.mentions[0].mention as { sourceRef: Record<string, unknown> };
    expect(m.sourceRef.episodeGuid).toBeNull();
    expect(m.sourceRef.timestamp).toBeNull();
    expect(m.sourceRef.transcriptSource).toBeNull();
    expect(work.mentions[0].episode).toBeNull();
  });

  it('joint chaque œuvre à ses similaires du même créateur', async () => {
    seed({
      sources: [SOURCE],
      items: [
        item('w1', { creator: 'Bong Joon-ho' }),
        item('w2', { creator: 'Bong Joon-ho' }),
        item('w3', { creator: 'Autre' }),
      ],
      mentions: [mention('m1', 'w1'), mention('m2', 'w2'), mention('m3', 'w3')],
      episodes: [episode('g1')],
    });

    const p = await paths();
    const first = p.find((x) => x.params.itemId === 'w1')!;
    const similar = first.props.similar as Array<{ id: string }>;
    expect(similar.map((s) => s.id)).toEqual(['w2']);
  });

  it('ne produit rien quand il n’y a aucune source', async () => {
    seed({ sources: [], items: [item('w1')], mentions: [mention('m1', 'w1')] });
    expect(await paths()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Rendu — compteurs
// ---------------------------------------------------------------------------
describe('page œuvre — libellé du compteur', () => {
  function seedWith(mentions: Entry[]): void {
    seed({
      sources: [SOURCE],
      items: [item('w1', { creator: 'Bong Joon-ho', year: 2019 })],
      mentions,
      episodes: [episode('g1'), episode('g2')],
    });
  }

  it('une seule reco → « Recommandée 1 fois »', async () => {
    seedWith([mention('m1', 'w1')]);
    expect(visibleText(await renderWork('w1'))).toContain('Recommandée 1 fois');
  });

  it('plusieurs recos → « Recommandée N fois »', async () => {
    seedWith([
      mention('m1', 'w1'),
      mention('m2', 'w1', { sourceRef: { sourceId: 'ubm', episodeGuid: 'g2' } }),
    ]);
    expect(visibleText(await renderWork('w1'))).toContain('Recommandée 2 fois');
  });

  it('une seule citation (0 reco) → « Mentionnée 1 fois »', async () => {
    seedWith([mention('m1', 'w1', { kind: 'citation' })]);
    const text = visibleText(await renderWork('w1'));
    expect(text).toContain('Mentionnée 1 fois');
    expect(text).not.toContain('Recommandée');
  });

  it('plusieurs citations (0 reco) → « Mentionnée N fois »', async () => {
    seedWith([
      mention('m1', 'w1', { kind: 'citation' }),
      mention('m2', 'w1', { kind: 'citation', sourceRef: { sourceId: 'ubm', episodeGuid: 'g2' } }),
    ]);
    expect(visibleText(await renderWork('w1'))).toContain('Mentionnée 2 fois');
  });

  it('le titre de section suit le total de MENTIONS (citations incluses)', async () => {
    seedWith([
      mention('m1', 'w1'),
      mention('m2', 'w1', { kind: 'citation', sourceRef: { sourceId: 'ubm', episodeGuid: 'g2' } }),
    ]);
    const text = visibleText(await renderWork('w1'));
    // 1 reco + 1 citation → « Recommandée 1 fois » mais « 2 mentions ».
    expect(text).toContain('Recommandée 1 fois');
    expect(text).toContain('2 mentions dans le podcast');
  });

  it('une mention unique → titre de section au singulier', async () => {
    seedWith([mention('m1', 'w1')]);
    expect(visibleText(await renderWork('w1'))).toContain('Mention dans le podcast');
  });

  it('badge « tendance » à partir de 2 mentions récentes', async () => {
    seedWith([
      mention('m1', 'w1'),
      mention('m2', 'w1', { sourceRef: { sourceId: 'ubm', episodeGuid: 'g2' } }),
    ]);
    expect(await renderWork('w1')).toContain('class="trending"');
  });

  it('pas de badge « tendance » avec une seule mention', async () => {
    seedWith([mention('m1', 'w1')]);
    expect(await renderWork('w1')).not.toContain('class="trending"');
  });
});

// ---------------------------------------------------------------------------
// Rendu — en-tête (types, créateur, année, réseaux sociaux)
// ---------------------------------------------------------------------------
describe('page œuvre — en-tête', () => {
  it('rend un emoji + un libellé par type connu', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { types: ['film', 'livre'] })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('🎬');
    expect(html).toContain('📖');
    expect(html).toContain('aria-label="Film, Livre"');
  });

  it('type inconnu → emoji ✨ et libellé brut', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { types: ['ovni'] })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('✨');
    expect(html).toContain('aria-label="ovni"');
  });

  it('créateur et année affichés quand présents', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { creator: 'Bong Joon-ho', year: 2019 })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('Bong Joon-ho');
    expect(html).toContain('· 2019');
    expect(html).toContain('aria-label="Année 2019"');
  });

  it('ni créateur ni année → aucun bloc parasite', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).not.toContain('class="creator"');
    expect(html).not.toContain('aria-label="Année');
  });

  it('handles Instagram / TikTok → liens externes en target=_blank', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { externalIds: { instagram: 'monhandle', tiktok: 'montiktok' } })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('https://www.instagram.com/monhandle/');
    expect(html).toContain('https://www.tiktok.com/@montiktok');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it('un handle non-textuel est ignoré (garde de type)', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { externalIds: { instagram: 42, tiktok: null } })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).not.toContain('instagram.com');
    expect(html).not.toContain('tiktok.com');
    expect(html).not.toContain('class="work-social"');
  });

  it('un seul handle suffit à afficher le bloc social', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { externalIds: { tiktok: 'seul' } })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('https://www.tiktok.com/@seul');
    expect(html).not.toContain('instagram.com');
  });
});

// ---------------------------------------------------------------------------
// Rendu — liens externes
// ---------------------------------------------------------------------------
describe('page œuvre — liens externes', () => {
  it('affiche les liens et marque leur classe éthique', async () => {
    seed({
      sources: [SOURCE],
      items: [
        item('w1', {
          customLinks: [{ label: 'Site officiel', url: 'https://exemple.fr/film' }],
          watchProviders: [
            { name: 'Indé', url: 'https://indie.example/x', ethics: 'indie' },
            { name: 'Géant', url: 'https://geant.example/x', ethics: 'avoid' },
          ],
        }),
      ],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('https://exemple.fr/film');
    expect(html).toContain('work-link indie');
    expect(html).toContain('work-link avoid');
    expect(html).toContain('aria-label="Liens externes"');
  });

  it('aucune liste de liens quand l’œuvre n’en a aucun', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });

    expect(await renderWork('w1')).not.toContain('class="work-links"');
  });

  it('un lien `javascript:` est filtré avant rendu', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { customLinks: [{ label: 'Piège', url: 'javascript:alert(1)' }] })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).not.toContain('javascript:');
    expect(html).not.toContain('class="work-links"');
  });
});

// ---------------------------------------------------------------------------
// Rendu — SEO (titre, description, JSON-LD) et œuvres similaires
// ---------------------------------------------------------------------------
describe('page œuvre — SEO et similaires', () => {
  it('titre et description intègrent le créateur quand il existe', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { creator: 'Bong Joon-ho' })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('<title>Titre w1 — Bong Joon-ho — Reco</title>');
    expect(html).toContain(
      '<meta name="description" content="Titre w1 (Bong Joon-ho) — Recommandée 1 fois dans le podcast Un Bon Moment.">',
    );
  });

  it('sans créateur, titre et description se replient sur le seul titre', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('<title>Titre w1 — Reco</title>');
    expect(html).toContain(
      '<meta name="description" content="Titre w1 — Recommandée 1 fois dans le podcast Un Bon Moment.">',
    );
  });

  it('description en mode « mention » quand il n’y a que des citations', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1', { kind: 'citation' })],
      episodes: [episode('g1')],
    });

    expect(await renderWork('w1')).toContain(
      '<meta name="description" content="Titre w1 — Mentionnée dans le podcast Un Bon Moment.">',
    );
  });

  it('description « Mentionnée N fois » au pluriel de citations', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [
        mention('m1', 'w1', { kind: 'citation' }),
        mention('m2', 'w1', { kind: 'citation', sourceRef: { sourceId: 'ubm', episodeGuid: 'g2' } }),
      ],
      episodes: [episode('g1'), episode('g2')],
    });

    expect(await renderWork('w1')).toContain(
      '<meta name="description" content="Titre w1 — Mentionnée 2 fois dans le podcast Un Bon Moment.">',
    );
  });

  it('JSON-LD typé selon le premier type, avec l’URL absolue de la page', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { types: ['film'], creator: 'Bong Joon-ho' })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const [schema] = jsonLdOf(await renderWork('w1'));

    expect(schema['@type']).toBe('Movie');
    expect(schema.url).toBe(`${TEST_SITE}/ubm/oeuvre/w1`);
    expect(schema.name).toBe('Titre w1');
  });

  it('type absent → JSON-LD de repli CreativeWork', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { types: [] })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const [schema] = jsonLdOf(await renderWork('w1'));

    expect(schema['@type']).toBe('CreativeWork');
  });

  it('l’image OG pointe la carte de la SOURCE, la seule qui existe', async () => {
    // Ce test exigeait `/og/ubm/oeuvre/w1.png` — une carte par œuvre que
    // `src/pages/og/[...slug].png.ts` n'a jamais générée. Il verrouillait donc
    // un défaut : les 1 036 pages d'œuvre du site déclaraient une image qui
    // répondait 404, et ce sont les plus partagées.
    //
    // Une carte par œuvre coûterait une cinquantaine de mégaoctets au build,
    // et les items ne portent aucune affiche à réutiliser. Mieux vaut une
    // carte juste et générique qu'une image absente. Cf.
    // `tests/build/test_og_images_existent.test.ts`, qui vérifie désormais sur
    // le site construit que toute `og:image` locale existe vraiment.
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain(`content="${TEST_SITE}/og/ubm.png"`);
    expect(html).not.toContain('/og/ubm/oeuvre/');
    expect(html).toContain('<meta property="og:type" content="article">');
  });

  it('section « Du même créateur » rendue avec les œuvres similaires', async () => {
    seed({
      sources: [SOURCE],
      items: [
        item('w1', { creator: 'Bong Joon-ho' }),
        item('w2', { creator: 'Bong Joon-ho' }),
      ],
      mentions: [mention('m1', 'w1'), mention('m2', 'w2')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(visibleText(html)).toContain('Du même créateur');
    expect(html).toContain('/ubm/oeuvre/w2');
  });

  it('pas de section « Du même créateur » sans œuvre apparentée', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1', { creator: 'Bong Joon-ho' })],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });

    expect(visibleText(await renderWork('w1'))).not.toContain('Du même créateur');
  });

  it('le thème de la source est appliqué et le lien de retour pointe la source', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'w1')],
      episodes: [episode('g1')],
    });
    const html = await renderWork('w1');

    expect(html).toContain('--accent:#ff5500');
    expect(html).toContain('href="/ubm"');
  });
});
