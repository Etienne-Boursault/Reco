/**
 * tests/gallery/test_page_invite_cov.test.ts
 *
 * Page `/[source]/invite/[name]` (`src/pages/[source]/invite/[name].astro`).
 *
 * Deux surfaces distinctes :
 *  1. `getStaticPaths` — c'est là qu'est la logique : croisement sources ×
 *     mentions, exclusion des hôtes, slugification, dédoublonnage des
 *     collisions de slug, isolation par source ;
 *  2. le rendu — filtrage `selectByGuest`, titre, compteur, JSON-LD
 *     (ItemList + fil d'Ariane dont le 3ᵉ niveau porte le nom de l'invité,
 *     pas le titre de la galerie).
 *
 * `astro:content` est mocké : aucun accès aux collections réelles.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText, TEST_SITE } from './_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import InvitePage, { getStaticPaths } from '../../src/pages/[source]/invite/[name].astro';

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

function seed(map: Partial<Record<'sources' | 'mentions' | 'items', Entry[]>>): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

function mention(itemId: string, by: string, sourceId = 'ubm', extra: Record<string, unknown> = {}) {
  return {
    data: {
      itemId,
      recommendedBy: by,
      sourceRef: { sourceId },
      kind: 'reco',
      status: 'validated',
      ...extra,
    },
  };
}

function item(id: string, title: string, types = ['film']) {
  return { data: { id, title, types, creator: 'Réal', year: 2019 } };
}

interface Path {
  params: { source: string; name: string };
  props: { source: { id: string }; guestName: string };
}

async function paths(): Promise<Path[]> {
  return (await getStaticPaths()) as unknown as Path[];
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

describe('/[source]/invite/[name] — getStaticPaths', () => {
  it('crée une route par invité, avec le slug en param et le nom en prop', async () => {
    seed({
      sources: [SOURCE],
      mentions: [mention('w1', 'Adrien Ménielle'), mention('w2', 'Adrien Ménielle')],
    });

    const p = await paths();
    expect(p).toHaveLength(1);
    expect(p[0].params).toEqual({ source: 'ubm', name: 'adrien-menielle' });
    expect(p[0].props.guestName).toBe('Adrien Ménielle');
    expect(p[0].props.source.id).toBe('ubm');
  });

  it('exclut les hôtes du podcast (pas de page invité pour un animateur)', async () => {
    seed({
      sources: [SOURCE],
      mentions: [mention('w1', 'Adèle'), mention('w2', 'Bruno')],
    });

    const p = await paths();
    expect(p.map((x) => x.props.guestName)).toEqual(['Bruno']);
  });

  it('tolère une source sans champ `hosts` (fallback tableau vide)', async () => {
    seed({
      sources: [{ id: 'ubm', data: { id: 'ubm', title: 'UBM' } }],
      mentions: [mention('w1', 'Bruno')],
    });

    const p = await paths();
    expect(p.map((x) => x.props.guestName)).toEqual(['Bruno']);
  });

  it('isole les invités par source (une mention d’une autre source ne fuit pas)', async () => {
    seed({
      sources: [SOURCE, { id: 'autre', data: { id: 'autre', title: 'Autre', hosts: [] } }],
      mentions: [mention('w1', 'Bruno', 'ubm'), mention('w2', 'Carla', 'autre')],
    });

    const p = await paths();
    expect(p.map((x) => [x.params.source, x.props.guestName])).toEqual([
      ['ubm', 'Bruno'],
      ['autre', 'Carla'],
    ]);
  });

  it('déduplique les collisions de slug (premier nom rencontré gagne)', async () => {
    seed({
      sources: [SOURCE],
      mentions: [mention('w1', 'Jean-Marc'), mention('w2', 'jean marc')],
    });

    const p = await paths();
    expect(p).toHaveLength(1);
    expect(p[0].params.name).toBe('jean-marc');
  });

  it('ignore les mentions `discarded` et les `recommendedBy` vides', async () => {
    seed({
      sources: [SOURCE],
      mentions: [
        mention('w1', 'Fantôme', 'ubm', { status: 'discarded' }),
        mention('w2', '   '),
        mention('w3', 'Bruno'),
      ],
    });

    const p = await paths();
    expect(p.map((x) => x.props.guestName)).toEqual(['Bruno']);
  });

  it('ne produit aucune route quand aucune mention ne porte d’invité', async () => {
    seed({ sources: [SOURCE], mentions: [] });
    expect(await paths()).toEqual([]);
  });
});

describe('/[source]/invite/[name] — rendu', () => {
  async function render(
    guestName: string,
    slug: string,
    data: { items: Entry[]; mentions: Entry[] },
  ): Promise<string> {
    seed({ sources: [SOURCE], items: data.items, mentions: data.mentions });
    return renderPage(InvitePage, {
      params: { source: 'ubm', name: slug },
      props: { source: SOURCE, guestName },
      path: `/ubm/invite/${slug}`,
    });
  }

  it('titre « Recommandations de <invité> » et intro nommant la source', async () => {
    const html = await render('Bruno', 'bruno', {
      items: [item('w1', 'Parasite')],
      mentions: [mention('w1', 'Bruno')],
    });

    expect(html).toMatch(/<h1[^>]*>Recommandations de Bruno<\/h1>/);
    // `<strong>` autour des noms → on tolère l'espace laissé par le
    // détagage (« Un Bon Moment . »).
    expect(visibleText(html)).toContain(
      'Toutes les œuvres recommandées par Bruno dans Un Bon Moment',
    );
  });

  it('ne garde que les œuvres recommandées par CET invité', async () => {
    const html = await render('Bruno', 'bruno', {
      items: [item('w1', 'Parasite'), item('w2', 'Portrait de la jeune fille')],
      mentions: [mention('w1', 'Bruno'), mention('w2', 'Carla')],
    });

    expect(html).toContain('Parasite');
    expect(html).not.toContain('Portrait de la jeune fille');
    // Une seule reco → compteur au SINGULIER.
    expect(visibleText(html)).toContain('1 recommandation');
    expect(visibleText(html)).not.toContain('1 recommandations');
  });

  it('accorde le compteur au pluriel dès deux recos', async () => {
    const html = await render('Bruno', 'bruno', {
      items: [item('w1', 'Parasite'), item('w2', 'Memories of Murder')],
      mentions: [mention('w1', 'Bruno'), mention('w2', 'Bruno')],
    });

    expect(visibleText(html)).toContain('2 recommandations');
  });

  it('la comparaison de nom est insensible à la casse et aux espaces', async () => {
    const html = await render('Bruno Dupont', 'bruno-dupont', {
      items: [item('w1', 'Parasite')],
      mentions: [mention('w1', '  bruno DUPONT ')],
    });

    expect(html).toContain('Parasite');
  });

  it('état vide quand l’invité n’a aucune reco dans cette source', async () => {
    const text = visibleText(
      await render('Bruno', 'bruno', {
        items: [item('w1', 'Parasite')],
        mentions: [mention('w1', 'Carla')],
      }),
    );

    // En français, 0 prend le SINGULIER (cf. src/utils/plural.ts).
    expect(text).toContain('0 recommandation');
    expect(text).not.toContain('0 recommandations');
    expect(text).toContain('Pas encore de recommandation pour cet invité.');
  });

  it('le fil d’Ariane pointe le slug de l’URL et nomme l’invité au 3ᵉ niveau', async () => {
    const html = await render('Adrien Ménielle', 'adrien-menielle', {
      items: [item('w1', 'Parasite')],
      mentions: [mention('w1', 'Adrien Ménielle')],
    });
    const crumb = jsonLdOf(html).find((b) => b['@type'] === 'BreadcrumbList') as {
      itemListElement: Array<{ name: string; item: string }>;
    };

    expect(crumb.itemListElement.map((e) => e.item)).toEqual([
      `${TEST_SITE}/`,
      `${TEST_SITE}/ubm`,
      `${TEST_SITE}/ubm/invite/adrien-menielle`,
    ]);
    // 3ᵉ niveau = le nom de l'invité (pas « Recommandations de … »).
    expect(crumb.itemListElement[2].name).toBe('Adrien Ménielle');
  });

  it('l’ItemList annonce le nombre de recos de l’invité', async () => {
    const html = await render('Bruno', 'bruno', {
      items: [item('w1', 'A'), item('w2', 'B')],
      mentions: [mention('w1', 'Bruno'), mention('w2', 'Bruno')],
    });
    const list = jsonLdOf(html).find((b) => b['@type'] === 'ItemList');

    expect(list!.numberOfItems).toBe(2);
    expect(list!.name).toBe('Recommandations de Bruno');
  });

  it('la meta description accorde le libellé, au singulier comme au pluriel', async () => {
    // Cette chaîne s'affiche en résultat de recherche : c'est là que
    // « 1 recommandations » était le plus visible.
    const une = await render('Bruno', 'bruno', {
      items: [item('w1', 'A')],
      mentions: [mention('w1', 'Bruno')],
    });
    expect(une).toContain(
      '<meta name="description" content="1 recommandation de Bruno dans Un Bon Moment.">',
    );

    const deux = await render('Bruno', 'bruno', {
      items: [item('w1', 'A'), item('w2', 'B')],
      mentions: [mention('w1', 'Bruno'), mention('w2', 'Bruno')],
    });
    expect(deux).toContain(
      '<meta name="description" content="2 recommandations de Bruno dans Un Bon Moment.">',
    );
  });
});
