/**
 * tests/gallery/test_pages_galerie_dynamique_cov.test.ts
 *
 * Les deux pages nées de la relecture du 2026-08-19 — « je souhaitais avoir un
 * accès par types comme /series mais pour chacun des types » :
 *
 *  - `/[source]/[galerie]` : la route dynamique qui sert les dix galeries sans
 *    fichier dédié (artistes, albums, BD, spectacles, vidéos, podcasts, jeux,
 *    lieux, applications, autres) ;
 *  - `/[source]/galeries` : leur sommaire, `noindex`.
 *
 * Ni l'une ni l'autre n'était exercée. La CI l'a vu par la couverture des
 * fonctions, tombée à 92,24 % contre un seuil de 95 %.
 *
 * CE QUE CES TESTS PROTÈGENT
 * --------------------------
 * Deux invariants que le corpus réel ne montre qu'après coup. D'abord, une
 * galerie dont AUCUNE œuvre ne porte le type ne doit pas être construite —
 * sinon `application` produirait une page vide et indexée. Ensuite, le
 * sommaire doit compter par la même fonction que les pages : il annonçait 450
 * films là où la page en montrait 198, faute d'écarter les mentions écartées.
 *
 * `astro:content` est mocké : aucune lecture des recos réelles.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText } from './_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import Galerie from '../../src/pages/[source]/[galerie].astro';
import * as galerieMod from '../../src/pages/[source]/[galerie].astro';
import Sommaire from '../../src/pages/[source]/galeries.astro';
import * as sommaireMod from '../../src/pages/[source]/galeries.astro';
import { GALERIES_PAR_TYPE } from '../../src/lib/gallery/typesGaleries';

const SOURCE = {
  id: 'ubm',
  data: {
    id: 'ubm',
    title: 'Un Bon Moment',
    hosts: ['Adèle'],
    theme: {
      colors: {
        bg: '#101010', surface: '#181818', text: '#fafafa',
        muted: '#999999', accent: '#ff5500',
      },
    },
  },
};

interface Entry { id?: string; data: Record<string, unknown> }

function seed(map: Partial<Record<'sources' | 'mentions' | 'items', Entry[]>>): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

/** Item + mention appariés. `status` permet de tester le cas « écartée ». */
function pair(
  id: string, title: string, types: string[],
  { sourceId = 'ubm', status = 'validated' } = {},
) {
  return {
    item: { data: { id, title, types, creator: 'Un Auteur', year: 2020 } },
    mention: {
      data: { itemId: id, sourceRef: { sourceId }, kind: 'reco', status },
    },
  };
}

function seedPairs(entries: ReturnType<typeof pair>[], sources: Entry[] = [SOURCE]): void {
  seed({
    sources,
    items: entries.map((e) => e.item),
    mentions: entries.map((e) => e.mention),
  });
}

const SPECTACLES = GALERIES_PAR_TYPE.find((g) => g.slug === 'spectacles')!;
const JEUX = GALERIES_PAR_TYPE.find((g) => g.slug === 'jeux')!;

interface Chemin {
  params: { source: string; galerie: string };
  props: { source: { id: string }; galerie: { slug: string } };
}

beforeEach(() => {
  getCollection.mockReset();
});

// ===== La route dynamique ==================================================
describe('/[source]/[galerie] — getStaticPaths', () => {
  it('ne construit QUE les galeries dont le corpus porte le type', async () => {
    seedPairs([pair('w1', 'Un spectacle', ['spectacle'])]);
    const paths = (await galerieMod.getStaticPaths()) as Chemin[];

    expect(paths.map((p) => p.params.galerie)).toEqual(['spectacles']);
  });

  it('laisse de côté une galerie vide plutôt que de la construire', async () => {
    // « application » n'est porté par aucune œuvre ici : la page serait vide
    // et indexée. Elle apparaîtra quand une œuvre portera le type.
    seedPairs([pair('w1', 'Un jeu', ['jeu'])]);
    const slugs = ((await galerieMod.getStaticPaths()) as Chemin[])
      .map((p) => p.params.galerie);

    expect(slugs).not.toContain('applications');
  });

  it('ne compte pas les mentions ÉCARTÉES', async () => {
    seedPairs([pair('w1', 'Refusée', ['jeu'], { status: 'discarded' })]);
    expect(await galerieMod.getStaticPaths()).toEqual([]);
  });

  it('ne compte pas les mentions d’une AUTRE source', async () => {
    seedPairs(
      [pair('w1', 'Chez eux', ['jeu'], { sourceId: 'autre' })],
      [SOURCE, { id: 'autre', data: { id: 'autre', title: 'Autre', hosts: [] } }],
    );
    const paths = (await galerieMod.getStaticPaths()) as Chemin[];

    expect(paths.map((p) => p.params.source)).toEqual(['autre']);
  });

  it('croise chaque source avec ses propres galeries', async () => {
    const mien = pair('w1', 'Mon jeu', ['jeu']);
    const leur = pair('w2', 'Leur spectacle', ['spectacle'], { sourceId: 'autre' });
    seedPairs(
      [mien, leur],
      [SOURCE, { id: 'autre', data: { id: 'autre', title: 'Autre', hosts: [] } }],
    );
    const paths = (await galerieMod.getStaticPaths()) as Chemin[];

    expect(paths.map((p) => `${p.params.source}/${p.params.galerie}`))
      .toEqual(['ubm/jeux', 'autre/spectacles']);
  });

  it('passe la galerie en props, pas seulement son slug', async () => {
    seedPairs([pair('w1', 'Un jeu', ['jeu'])]);
    const [chemin] = (await galerieMod.getStaticPaths()) as Chemin[];

    expect(chemin.props.galerie.slug).toBe('jeux');
    expect(chemin.props.source.id).toBe('ubm');
  });

  it('ne produit rien quand aucune source n’est déclarée', async () => {
    seed({ sources: [] });
    expect(await galerieMod.getStaticPaths()).toEqual([]);
  });
});

describe('/[source]/[galerie] — rendu', () => {
  async function rendre(
    entries: ReturnType<typeof pair>[],
    galerie = SPECTACLES,
  ): Promise<string> {
    seedPairs(entries);
    return renderPage(Galerie, {
      params: { source: SOURCE.id, galerie: galerie.slug },
      props: { source: SOURCE, galerie },
      path: `/${SOURCE.id}/${galerie.slug}`,
    });
  }

  it('rend le titre de la galerie et le retour vers la source', async () => {
    const html = await rendre([pair('w1', 'Un spectacle', ['spectacle'])]);

    expect(html).toMatch(/<h1[^>]*>Tous les spectacles<\/h1>/);
    expect(html).toContain('href="/ubm"');
    expect(visibleText(html)).toContain('retour au podcast Un Bon Moment');
  });

  it('ne retient que les œuvres du type de la galerie', async () => {
    const html = await rendre([
      pair('w1', 'Gardée', ['spectacle']),
      pair('w2', 'Absente', ['jeu']),
    ]);

    expect(html).toContain('Gardée');
    expect(html).not.toContain('Absente');
  });

  it('accorde le compteur au singulier à une entrée', async () => {
    const html = await rendre([pair('w1', 'Seule', ['spectacle'])]);
    expect(visibleText(html)).toContain('1 spectacle recommandé');
  });

  it('accorde le compteur au pluriel dès deux entrées', async () => {
    const html = await rendre([
      pair('w1', 'Une', ['spectacle']),
      pair('w2', 'Deux', ['spectacle']),
    ]);

    expect(visibleText(html)).toContain('2 spectacles recommandés');
  });

  it('affiche le message d’état vide quand rien ne sort', async () => {
    const html = await rendre([pair('w1', 'Ailleurs', ['jeu'])]);
    expect(visibleText(html)).toContain('Aucun spectacle recommandé');
  });

  it('emploie le PLURIEL accordé dans la phrase d’en-tête', async () => {
    // « Les bandes dessinées recommandées dans … » : « Toutes les BD » ne
    // permettrait pas de recoller l'accord.
    const bd = GALERIES_PAR_TYPE.find((g) => g.slug === 'bd')!;
    const html = await rendre([pair('w1', 'Une BD', ['bd'])], bd);

    expect(visibleText(html)).toContain('Les bandes dessinées recommandées dans');
  });

  it('émet un ItemList et un fil d’Ariane en JSON-LD', async () => {
    const html = await rendre([pair('w1', 'Un jeu', ['jeu'])], JEUX);
    const bloc = html.match(
      /<script type="application\/ld\+json">([\s\S]*?)<\/script>/,
    );
    const jsonLd = JSON.parse(bloc![1]) as Record<string, unknown>[];

    expect(jsonLd.map((s) => s['@type'])).toEqual(['ItemList', 'BreadcrumbList']);
    expect(jsonLd[0].name).toBe('Tous les jeux');
  });
});

// ===== Le sommaire =========================================================
describe('/[source]/galeries', () => {
  async function rendre(entries: ReturnType<typeof pair>[]): Promise<string> {
    seedPairs(entries);
    return renderPage(Sommaire, {
      params: { source: SOURCE.id },
      props: { source: SOURCE },
      path: `/${SOURCE.id}/galeries`,
    });
  }

  it('getStaticPaths émet une page par source', async () => {
    seed({
      sources: [SOURCE, { id: 'autre', data: { id: 'autre', title: 'Autre', hosts: [] } }],
    });
    const paths = (await sommaireMod.getStaticPaths()) as Array<{
      params: { source: string };
    }>;

    expect(paths.map((p) => p.params.source)).toEqual(['ubm', 'autre']);
  });

  it('nomme le type seul, sans « Tous les… »', async () => {
    // « mets simplement le type » : quatorze entrées alignées répétaient un
    // article que la colonne rendait inutile.
    const html = await rendre([pair('w1', 'Un film', ['film'])]);
    const texte = visibleText(html);

    expect(texte).toContain('Films');
    expect(texte).not.toContain('Tous les films');
  });

  it('écarte les mentions écartées du compte annoncé', async () => {
    // Le sommaire annonçait 450 films là où la page en montrait 198.
    const html = await rendre([
      pair('w1', 'Publiée', ['film']),
      pair('w2', 'Écartée', ['film'], { status: 'discarded' }),
    ]);

    expect(visibleText(html)).toMatch(/Films\s*1\b/);
  });

  it('ne liste pas une galerie que le corpus ne porte pas', async () => {
    const html = await rendre([pair('w1', 'Un film', ['film'])]);
    expect(visibleText(html)).not.toContain('Applications');
  });

  it('classe les galeries de la plus fournie à la moins fournie', async () => {
    const html = await rendre([
      pair('w1', 'Jeu 1', ['jeu']),
      pair('w2', 'Jeu 2', ['jeu']),
      pair('w3', 'Un film', ['film']),
    ]);
    const texte = visibleText(html);

    expect(texte.indexOf('Jeux')).toBeLessThan(texte.indexOf('Films'));
  });

  it('renvoie vers la page de chaque galerie', async () => {
    const html = await rendre([pair('w1', 'Un jeu', ['jeu'])]);
    expect(html).toContain('href="/ubm/jeux"');
  });

  it('est en noindex — c’est une page de relecture', async () => {
    const html = await rendre([pair('w1', 'Un jeu', ['jeu'])]);
    expect(html).toMatch(/<meta[^>]+name="robots"[^>]+noindex/);
  });

  it('borne l’échantillon d’œuvres à vingt-quatre', async () => {
    // Les lister toutes ferait 1 092 liens, ce qui n'aiderait personne.
    const beaucoup = Array.from({ length: 30 }, (_, i) =>
      pair(`w${i}`, `Œuvre ${String(i).padStart(2, '0')}`, ['jeu']));
    const html = await rendre(beaucoup);
    const listees = beaucoup.filter((e) =>
      html.includes(`/oeuvre/${(e.item.data as { id: string }).id}"`));

    expect(listees).toHaveLength(24);
  });
});
