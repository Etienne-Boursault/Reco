/**
 * tests/gallery/test_pages_galleries_cov.test.ts
 *
 * Les cinq pages galerie de `src/pages/[source]/` — `chaines`, `films`,
 * `livres`, `musique`, `series` — partagent exactement le même squelette :
 * `getStaticPaths` (1 page / source), filtrage mentions → items, appel à
 * `selectByType` avec une liste de types propre à chaque galerie, puis rendu
 * `Layout` + `GalleryGrid` + JSON-LD (ItemList + BreadcrumbList).
 *
 * On les teste donc **en table** : un seul corps de test par comportement,
 * paramétré par la galerie. Les rares différences (liste de types, libellés,
 * `emptyHint` présent uniquement sur `films`) sont des colonnes de la table.
 *
 * `astro:content` est mocké : aucune lecture des 3008 recos réelles.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText, TEST_SITE } from './_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import Chaines from '../../src/pages/[source]/chaines.astro';
import Films from '../../src/pages/[source]/films.astro';
import Livres from '../../src/pages/[source]/livres.astro';
import Musique from '../../src/pages/[source]/musique.astro';
import Series from '../../src/pages/[source]/series.astro';
import * as chainesMod from '../../src/pages/[source]/chaines.astro';
import * as filmsMod from '../../src/pages/[source]/films.astro';
import * as livresMod from '../../src/pages/[source]/livres.astro';
import * as musiqueMod from '../../src/pages/[source]/musique.astro';
import * as seriesMod from '../../src/pages/[source]/series.astro';

interface GallerySpec {
  /** Segment d'URL de la galerie (`films`, `livres`, …). */
  slug: string;
  Page: unknown;
  mod: { getStaticPaths: () => Promise<unknown[]> };
  /** `<h1>` attendu (i18n `gallery.<x>.title`). */
  heading: string;
  /** Libellé du compteur rendu par `GalleryGrid`. */
  countLabel: string;
  /** Un type d'item qui DOIT être retenu par cette galerie. */
  keptType: string;
  /** Un type d'item qui NE doit PAS l'être. */
  rejectedType: string;
  /** Message d'état vide. */
  emptyMessage: string;
}

const GALLERIES: GallerySpec[] = [
  {
    slug: 'chaines',
    Page: Chaines,
    mod: chainesMod as never,
    heading: 'Toutes les chaînes YouTube',
    countLabel: 'chaînes YouTube recommandées',
    keptType: 'chaine',
    rejectedType: 'film',
    emptyMessage: "Aucune chaîne YouTube recommandée pour l'instant.",
  },
  {
    slug: 'films',
    Page: Films,
    mod: filmsMod as never,
    heading: 'Tous les films',
    countLabel: 'films recommandés',
    keptType: 'film',
    rejectedType: 'livre',
    emptyMessage: "Aucun film recommandé pour l'instant.",
  },
  {
    slug: 'livres',
    Page: Livres,
    mod: livresMod as never,
    heading: 'Tous les livres',
    countLabel: 'livres et BD recommandés',
    keptType: 'livre',
    rejectedType: 'film',
    emptyMessage: "Aucun livre recommandé pour l'instant.",
  },
  {
    slug: 'musique',
    Page: Musique,
    mod: musiqueMod as never,
    heading: 'Toute la musique',
    countLabel: 'œuvres musicales recommandées',
    keptType: 'album',
    rejectedType: 'film',
    emptyMessage: "Aucune œuvre musicale recommandée pour l'instant.",
  },
  {
    slug: 'series',
    Page: Series,
    mod: seriesMod as never,
    heading: 'Toutes les séries',
    countLabel: 'séries recommandées',
    keptType: 'serie',
    rejectedType: 'film',
    emptyMessage: "Aucune série recommandée pour l'instant.",
  },
];

const SOURCE = {
  id: 'ubm',
  data: {
    id: 'ubm',
    title: 'Un Bon Moment',
    hosts: ['Adèle'],
    theme: {
      colors: {
        bg: '#101010',
        surface: '#181818',
        text: '#fafafa',
        muted: '#999999',
        accent: '#ff5500',
      },
    },
  },
};

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

function seed(map: Partial<Record<'sources' | 'mentions' | 'items', Entry[]>>): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

/** Item + mention appariés dans la source `ubm`. */
function pair(id: string, title: string, types: string[], sourceId = 'ubm') {
  return {
    item: { data: { id, title, types, creator: 'Un Auteur', year: 2020 } },
    mention: {
      data: { itemId: id, sourceRef: { sourceId }, kind: 'reco', status: 'validated' },
    },
  };
}

/** Extrait les blocs JSON-LD (`<script type="application/ld+json">`). */
function jsonLdOf(html: string): Record<string, unknown>[] {
  const m = html.match(
    /<script type="application\/ld\+json">([\s\S]*?)<\/script>/,
  );
  if (!m) return [];
  const parsed = JSON.parse(m[1]);
  return Array.isArray(parsed) ? parsed : [parsed];
}

beforeEach(() => {
  getCollection.mockReset();
});

describe.each(GALLERIES)(
  'Page galerie /[source]/$slug',
  ({ slug, Page, mod, heading, countLabel, keptType, rejectedType, emptyMessage }) => {
    async function render(entries: ReturnType<typeof pair>[]): Promise<string> {
      seed({
        sources: [SOURCE],
        items: entries.map((e) => e.item),
        mentions: entries.map((e) => e.mention),
      });
      return renderPage(Page, {
        params: { source: SOURCE.id },
        props: { source: SOURCE },
        path: `/${SOURCE.id}/${slug}`,
      });
    }

    it('getStaticPaths émet une page par source, avec la source en props', async () => {
      seed({
        sources: [
          SOURCE,
          { id: 'autre', data: { id: 'autre', title: 'Autre Podcast', hosts: [] } },
        ],
      });
      const paths = (await mod.getStaticPaths()) as Array<{
        params: { source: string };
        props: { source: { id: string } };
      }>;

      expect(paths.map((p) => p.params.source)).toEqual(['ubm', 'autre']);
      expect(paths[0].props.source.id).toBe('ubm');
    });

    it('getStaticPaths ne produit rien quand aucune source n’est déclarée', async () => {
      seed({ sources: [] });
      expect(await mod.getStaticPaths()).toEqual([]);
    });

    it('rend le h1 de la galerie et le lien de retour vers la source', async () => {
      const html = await render([pair('w1', 'Œuvre A', [keptType])]);

      expect(html).toMatch(new RegExp(`<h1[^>]*>${heading}</h1>`));
      expect(html).toContain('href="/ubm"');
      expect(visibleText(html)).toContain('retour au podcast Un Bon Moment');
    });

    it('ne retient que les items du/des type(s) de la galerie', async () => {
      const html = await render([
        pair('w1', 'Gardée', [keptType]),
        pair('w2', 'Écartée', [rejectedType]),
      ]);

      expect(html).toContain('Gardée');
      expect(html).not.toContain('Écartée');
      expect(visibleText(html)).toContain(`1 ${countLabel}`);
    });

    it('ignore les mentions rattachées à une AUTRE source', async () => {
      const mine = pair('w1', 'Chez nous', [keptType]);
      const theirs = pair('w2', 'Chez eux', [keptType], 'autre-podcast');
      seed({
        sources: [SOURCE],
        items: [mine.item, theirs.item],
        mentions: [mine.mention, theirs.mention],
      });
      const html = await renderPage(Page, {
        params: { source: SOURCE.id },
        props: { source: SOURCE },
        path: `/${SOURCE.id}/${slug}`,
      });

      expect(html).toContain('Chez nous');
      expect(html).not.toContain('Chez eux');
    });

    it('écarte un item du bon type mais sans aucune mention', async () => {
      seed({
        sources: [SOURCE],
        items: [{ data: { id: 'orphelin', title: 'Jamais citée', types: [keptType] } }],
        mentions: [],
      });
      const html = await renderPage(Page, {
        params: { source: SOURCE.id },
        props: { source: SOURCE },
        path: `/${SOURCE.id}/${slug}`,
      });

      expect(html).not.toContain('Jamais citée');
      expect(visibleText(html)).toContain(emptyMessage);
    });

    it('affiche l’état vide (0 entrée) avec le message dédié', async () => {
      const text = visibleText(await render([]));

      expect(text).toContain(`0 ${countLabel}`);
      expect(text).toContain(emptyMessage);
    });

    it('la description meta annonce le nombre d’entrées et la source', async () => {
      const html = await render([
        pair('w1', 'A', [keptType]),
        pair('w2', 'B', [keptType]),
      ]);

      expect(html).toMatch(
        new RegExp(`<meta name="description" content="2 [^"]*Un Bon Moment\\.">`),
      );
    });

    it('émet un ItemList + un BreadcrumbList à 3 niveaux, en URLs absolues', async () => {
      const html = await render([pair('w1', 'Œuvre A', [keptType])]);
      const blocks = jsonLdOf(html);

      const itemList = blocks.find((b) => b['@type'] === 'ItemList');
      expect(itemList).toBeDefined();
      expect(itemList!.name).toBe(heading);
      expect(itemList!.numberOfItems).toBe(1);

      const crumb = blocks.find((b) => b['@type'] === 'BreadcrumbList') as {
        itemListElement: Array<{ position: number; name: string; item: string }>;
      };
      expect(crumb.itemListElement.map((e) => e.item)).toEqual([
        `${TEST_SITE}/`,
        `${TEST_SITE}/ubm`,
        `${TEST_SITE}/ubm/${slug}`,
      ]);
      expect(crumb.itemListElement[1].name).toBe('Un Bon Moment');
      expect(crumb.itemListElement[2].name).toBe(heading);
    });

    it('transmet le thème de la source et l’ogSlug au Layout', async () => {
      const html = await render([pair('w1', 'Œuvre A', [keptType])]);

      // theme.colors → variables CSS inline sur <html>.
      expect(html).toContain('--accent:#ff5500');
      // ogSlug = source.id → carte OG dédiée.
      expect(html).toContain(`content="${TEST_SITE}/og/ubm.png"`);
      expect(html).toContain(`<link rel="canonical" href="${TEST_SITE}/ubm/${slug}">`);
    });

    it('les cartes pointent vers la fiche œuvre de la source', async () => {
      const html = await render([pair('w1', 'Œuvre A', [keptType])]);

      expect(html).toContain('/ubm/oeuvre/w1');
    });
  },
);

// ---------------------------------------------------------------------------
// Différences assumées entre galeries (la table ci-dessus les gomme).
// ---------------------------------------------------------------------------
describe('Galeries — particularités par page', () => {
  async function renderWith(
    Page: unknown,
    slug: string,
    items: Entry[],
    mentions: Entry[],
  ): Promise<string> {
    seed({ sources: [SOURCE], items, mentions });
    return renderPage(Page, {
      params: { source: SOURCE.id },
      props: { source: SOURCE },
      path: `/ubm/${slug}`,
    });
  }

  it('livres englobe les BD (types livre ET bd)', async () => {
    const a = pair('w1', 'Un roman', ['livre']);
    const b = pair('w2', 'Une BD', ['bd']);
    const html = await renderWith(Livres, 'livres', [a.item, b.item], [a.mention, b.mention]);

    expect(html).toContain('Un roman');
    expect(html).toContain('Une BD');
    expect(visibleText(html)).toContain('2 livres et BD recommandés');
  });

  it('musique englobe musique, album et artiste', async () => {
    const a = pair('w1', 'Un morceau', ['musique']);
    const b = pair('w2', 'Un album', ['album']);
    const c = pair('w3', 'Un artiste', ['artiste']);
    const html = await renderWith(
      Musique,
      'musique',
      [a.item, b.item, c.item],
      [a.mention, b.mention, c.mention],
    );

    expect(html).toContain('Un morceau');
    expect(html).toContain('Un album');
    expect(html).toContain('Un artiste');
    expect(visibleText(html)).toContain('3 œuvres musicales recommandées');
  });

  it('films est la seule galerie à afficher un `emptyHint` (pipeline)', async () => {
    const filmsText = visibleText(await renderWith(Films, 'films', [], []));
    const seriesText = visibleText(await renderWith(Series, 'series', [], []));

    expect(filmsText).toContain("Lance le pipeline d'extraction");
    expect(seriesText).not.toContain("Lance le pipeline d'extraction");
  });

  it('chaines ne retient pas les vidéos (type `video` ≠ `chaine`)', async () => {
    const chaine = pair('w1', 'Une chaîne', ['chaine']);
    const video = pair('w2', 'Une vidéo', ['video']);
    const html = await renderWith(
      Chaines,
      'chaines',
      [chaine.item, video.item],
      [chaine.mention, video.mention],
    );

    expect(html).toContain('Une chaîne');
    expect(html).not.toContain('Une vidéo');
  });

  it('un item multi-types apparaît dans chaque galerie concernée', async () => {
    const both = pair('w1', 'Adaptation', ['film', 'livre']);
    const filmsHtml = await renderWith(Films, 'films', [both.item], [both.mention]);
    const livresHtml = await renderWith(Livres, 'livres', [both.item], [both.mention]);

    expect(filmsHtml).toContain('Adaptation');
    expect(livresHtml).toContain('Adaptation');
  });
});
