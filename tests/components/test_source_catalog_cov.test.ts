/**
 * Tests de rendu `src/components/SourceCatalog.astro` via l'Astro Container API.
 *
 * Le catalogue est le cœur du site : header de source, onglets « Par épisode »
 * / « Toutes les recos », chips de filtres construites depuis la fréquence des
 * types, miniatures d'épisodes (vignette YouTube → artwork Acast → rien) et
 * JSON-LD (PodcastSeries + fil d'Ariane, ce dernier omis en mode mono-source).
 *
 * `astro:content` est mocké à la frontière : aucune lecture disque des
 * collections. On vérifie que le composant filtre correctement par source,
 * masque les `discarded` et exclut les citations du compteur principal.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

const { renderWithSite } = await import('./_container');
const SourceCatalog = (await import('../../src/components/SourceCatalog.astro')).default;

interface Entry {
  data: Record<string, unknown>;
}
const entry = (data: Record<string, unknown>): Entry => ({ data });

const SOURCE = {
  id: 'ubm',
  data: {
    title: 'Un Bon Moment',
    description: 'Le podcast',
    tagline: 'Des invités, des recos',
    rssUrl: 'https://feeds.acast.com/ubm',
    theme: { colors: { bg: '#101014', surface: '#1b1b22', text: '#fff', muted: '#999', accent: '#ffd23f' } },
  },
};

const reco = (over: Record<string, unknown> = {}) =>
  entry({
    id: 'ubm-0001',
    sourceId: { id: 'ubm' },
    episodeGuid: 'ep-1',
    title: 'Parasite',
    creator: 'Bong Joon-ho',
    types: ['film'],
    status: 'validated',
    ...over,
  });

const episode = (over: Record<string, unknown> = {}) =>
  entry({
    guid: 'ep-1',
    sourceId: { id: 'ubm' },
    number: 12,
    title: 'Épisode douze',
    date: new Date('2026-03-01T00:00:00Z'),
    ...over,
  });

/** Programme les 3 collections lues (recos, episodes, sources). */
function collections(recos: Entry[], episodes: Entry[], sources: Entry[] = []) {
  getCollection.mockImplementation(async (name: string) => {
    if (name === 'recos') return recos;
    if (name === 'episodes') return episodes;
    return sources;
  });
}

async function render(
  props: Record<string, unknown> = {},
): Promise<string> {
  return renderWithSite(SourceCatalog, { props: { source: SOURCE, ...props } });
}

beforeEach(() => {
  getCollection.mockReset();
  collections([reco()], [episode()]);
});

describe('SourceCatalog — header de source', () => {
  it('affiche le titre, la tagline et le compteur de recommandations', async () => {
    const html = await render();
    expect(html).toContain('Un Bon Moment');
    expect(html).toContain('Des invités, des recos');
    expect(html).toMatch(/1 recommandation\s*<\/p>/);
  });

  it('accorde le pluriel du compteur à partir de 2 recos', async () => {
    collections([reco(), reco({ id: 'ubm-0002', title: 'Fez' })], [episode()]);
    const html = await render();
    expect(html).toMatch(/2 recommandations\s*<\/p>/);
  });

  it('sans tagline, aucun paragraphe .tag', async () => {
    collections([reco()], [episode()]);
    const html = await renderWithSite(SourceCatalog, {
      props: { source: { ...SOURCE, data: { ...SOURCE.data, tagline: undefined } } },
    });
    expect(html).not.toContain('class="tag"');
  });
});

describe('SourceCatalog — lien retour & mode mono-source (isHome)', () => {
  it('par défaut, affiche le lien « retour » vers la racine', async () => {
    const html = await render();
    expect(html).toMatch(/class="back"[^>]*href="\/"/);
    expect(html).toContain('tous les podcasts');
  });

  it('isHome=true masque le lien retour (le catalogue EST la racine)', async () => {
    const html = await render({ isHome: true });
    expect(html).not.toContain('class="back"');
  });

  it('isHome=false → JSON-LD PodcastSeries + BreadcrumbList', async () => {
    const html = await render();
    expect(html).toContain('"@type":"PodcastSeries"');
    expect(html).toContain('"@type":"BreadcrumbList"');
    expect(html).toContain('https://reco.example/ubm');
  });

  it('isHome=true → JSON-LD réduit au PodcastSeries, URL canonique sur /', async () => {
    const html = await render({ isHome: true });
    expect(html).toContain('"@type":"PodcastSeries"');
    expect(html).not.toContain('BreadcrumbList');
    expect(html).toContain('"url":"https://reco.example/"');
  });
});

describe('SourceCatalog — description SEO de repli', () => {
  it('utilise la description de la source quand elle existe', async () => {
    const html = await render();
    expect(html).toContain('content="Le podcast"');
  });

  it('sans description, compose une phrase accordée au nombre', async () => {
    collections([reco(), reco({ id: 'ubm-0002' })], [episode(), episode({ guid: 'ep-2', number: 13 })]);
    const html = await renderWithSite(SourceCatalog, {
      props: { source: { ...SOURCE, data: { ...SOURCE.data, description: undefined } } },
    });
    expect(html).toContain('2 recommandations extraites de 2 épisodes du podcast Un Bon Moment.');
  });

  it('singulier quand une seule reco et un seul épisode', async () => {
    collections([reco()], [episode()]);
    const html = await renderWithSite(SourceCatalog, {
      props: { source: { ...SOURCE, data: { ...SOURCE.data, description: undefined } } },
    });
    expect(html).toContain('1 recommandation extraite de 1 épisode du podcast Un Bon Moment.');
  });
});

describe('SourceCatalog — filtrage des recos', () => {
  it('ignore les recos d’une autre source', async () => {
    collections(
      [reco(), reco({ id: 'other-1', sourceId: { id: 'autre' }, title: 'Hors périmètre' })],
      [episode()],
    );
    const html = await render();
    expect(html).not.toContain('Hors périmètre');
    expect(html).toMatch(/1 recommandation\s*<\/p>/);
  });

  it('masque les recos discarded', async () => {
    collections(
      [reco(), reco({ id: 'ubm-9', title: 'Faux positif', status: 'discarded' })],
      [episode()],
    );
    const html = await render();
    expect(html).not.toContain('Faux positif');
  });

  it('les citations restent affichées mais hors du compteur principal', async () => {
    collections(
      [reco(), reco({ id: 'ubm-2', title: 'Simple citation', kind: 'citation' })],
      [episode()],
    );
    const html = await render();
    expect(html).toContain('Simple citation');
    expect(html).toMatch(/1 recommandation\s*<\/p>/);
  });

  it('aucune reco → état vide au lieu de la grille', async () => {
    collections([], [episode()]);
    const html = await render();
    expect(html).toContain('Pas encore de recommandation.');
    expect(html).toContain('tools/README.md');
    expect(html).not.toContain('id="reco-grid"');
  });
});

describe('SourceCatalog — chips de filtres par type', () => {
  it('trie les types par fréquence décroissante et affiche le compte', async () => {
    collections(
      [
        reco({ id: 'a', types: ['livre'] }),
        reco({ id: 'b', types: ['film'] }),
        reco({ id: 'c', types: ['film'] }),
      ],
      [episode()],
    );
    const html = await render();
    const filmIdx = html.indexOf('data-filter="film"');
    const livreIdx = html.indexOf('data-filter="livre"');
    expect(filmIdx).toBeGreaterThan(-1);
    expect(livreIdx).toBeGreaterThan(filmIdx);
    expect(html).toMatch(/Films <span class="n"[^>]*>2<\/span>/);
  });

  it('une reco multi-types compte dans chaque type (filtre inclusif)', async () => {
    collections([reco({ types: ['film', 'livre'] })], [episode()]);
    const html = await render();
    expect(html).toContain('data-filter="film"');
    expect(html).toContain('data-filter="livre"');
  });

  it('un type inconnu retombe sur sa clé brute comme libellé', async () => {
    collections([reco({ types: ['zarbi'] })], [episode()]);
    const html = await render();
    expect(html).toMatch(/data-filter="zarbi"[^>]*>\s*zarbi/);
  });
});

describe('SourceCatalog — vue « Par épisode »', () => {
  it('liste tous les épisodes, même sans reco validée', async () => {
    collections([], [episode(), episode({ guid: 'ep-2', number: 21, title: 'McFly & Carlito' })]);
    const html = await render();
    // Le titre est bien échappé — mais la FORME de l'échappement dépend de la
    // version d'Astro (`&#38;` en 5, `&amp;` en 7), pour un HTML sémantiquement
    // identique. Ce qui compte ici : l'esperluette est échappée (pas de `&`
    // nu, qui serait une faille d'injection) et le titre est présent en entier.
    expect(html).toMatch(/McFly &(?:#38|amp); Carlito/);
    expect(html).not.toContain('McFly & Carlito');
    expect(html).toContain('2 épisodes');
  });

  it('trie du plus récent au plus ancien, les épisodes sans date en dernier', async () => {
    collections(
      [],
      [
        episode({ guid: 'old', number: 1, title: 'Ancien', date: new Date('2024-01-01') }),
        episode({ guid: 'nodate', number: 2, title: 'Sans date', date: undefined }),
        episode({ guid: 'new', number: 3, title: 'Récent', date: new Date('2026-06-01') }),
      ],
    );
    const html = await render();
    expect(html.indexOf('Récent')).toBeLessThan(html.indexOf('Ancien'));
    expect(html.indexOf('Ancien')).toBeLessThan(html.indexOf('Sans date'));
  });

  it('compte les recos par épisode (0 quand aucune)', async () => {
    collections([reco()], [episode(), episode({ guid: 'ep-2', number: 13 })]);
    const html = await render();
    expect(html).toContain('1 reco');
    expect(html).toContain('0 reco');
  });

  it('affiche le titre FR du flux, pas le titre YouTube', async () => {
    collections([], [episode({ title: 'Titre français', youtubeTitle: 'A Good Time with BROUTE' })]);
    const html = await render();
    expect(html).toContain('Titre français');
    expect(html).not.toMatch(/<h3 class="ep-ttl"[^>]*>A Good Time/);
  });

  it('la clé de recherche inclut le titre YouTube, sans accents et en minuscules', async () => {
    collections([], [episode({ title: 'Épisode Été', youtubeTitle: 'Summer Show' })]);
    const html = await render();
    expect(html).toMatch(/data-search="episode ete summer show #12"/);
  });

  it('sans titre YouTube, la clé de recherche ne contient pas « undefined »', async () => {
    collections([], [episode({ title: 'Sobre', youtubeTitle: undefined })]);
    const html = await render();
    expect(html).toMatch(/data-search="sobre {2}#12"/);
    expect(html).not.toContain('undefined');
  });
});

describe('SourceCatalog — miniatures d’épisode', () => {
  it('vignette YouTube dérivée de l’URL watch?v=', async () => {
    collections([], [episode({ youtubeUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' })]);
    const html = await render();
    expect(html).toContain('https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg');
  });

  it('URL YouTube sans paramètre v → repli sur l’artwork Acast', async () => {
    collections(
      [],
      [episode({ youtubeUrl: 'https://youtu.be/abc', imageUrl: 'https://acast.example/art.jpg' })],
    );
    const html = await render();
    expect(html).not.toContain('i.ytimg.com');
    expect(html).toContain('https://acast.example/art.jpg');
  });

  it('sans URL YouTube, l’artwork Acast est utilisé', async () => {
    collections([], [episode({ imageUrl: 'https://acast.example/art.jpg' })]);
    const html = await render();
    expect(html).toContain('https://acast.example/art.jpg');
  });

  it('sans vignette ni artwork, aucune <img> n’est rendue', async () => {
    collections([], [episode()]);
    const html = await render();
    expect(html).not.toContain('<img');
  });

  it('les miniatures sont en lazy loading avec alt vide (décoratif)', async () => {
    collections([], [episode({ imageUrl: 'https://acast.example/art.jpg' })]);
    const html = await render();
    expect(html).toMatch(/<img[^>]*alt=""[^>]*loading="lazy"/);
  });
});

describe('SourceCatalog — libellé d’épisode (badge + nom accessible)', () => {
  it('numéro seul → badge #12 et aria-label préfixé', async () => {
    collections([], [episode({ number: 12, title: 'Douze' })]);
    const html = await render();
    expect(html).toContain('>#12</span>');
    expect(html).toContain('aria-label="#12 — Douze"');
  });

  it('saison + numéro → badge S1·E12', async () => {
    collections([], [episode({ season: 1, number: 12, title: 'Douze' })]);
    const html = await render();
    expect(html).toContain('>S1·E12</span>');
    expect(html).toContain('aria-label="S1·E12 — Douze"');
  });

  it('sans numéro : pas de badge, aria-label réduit au titre', async () => {
    collections([], [episode({ number: undefined, title: 'Hors série' })]);
    const html = await render();
    expect(html).not.toContain('ep-badge');
    expect(html).toContain('aria-label="Hors série"');
  });
});

describe('SourceCatalog — structure a11y (onglets, live regions)', () => {
  it('un tablist avec 2 onglets, roving tabindex et vue « Par épisode » active', async () => {
    const html = await render();
    expect(html).toContain('role="tablist"');
    expect(html).toMatch(/id="tab-episodes"[^>]*aria-selected="true"/);
    expect(html).toMatch(/id="tab-all"[^>]*aria-selected="false"/);
    expect(html).toMatch(/id="view-all"[^>]*hidden/);
  });

  // Ces deux régions sont un markup dupliqué mot pour mot (seul l'`id`
  // change). Faute de les factoriser — cf. le rapport : les sortir dans un
  // composant enfant leur ferait perdre le style scopé de cette page —, on
  // verrouille ici le trio ARIA sur CHACUNE, pour qu'une dérive de l'une
  // par rapport à l'autre casse un test.
  it.each(['noresult', 'ep-noresult'])(
    'la zone « aucun résultat » #%s porte le trio ARIA complet',
    async (id) => {
      const html = await render();
      const balise = html.match(new RegExp(`<p[^>]*id="${id}"[^>]*>`))?.[0] ?? '';
      expect(balise).toContain('role="status"');
      expect(balise).toContain('aria-live="polite"');
      expect(balise).toContain('aria-atomic="true"');
      // C7 : jamais masquée ni clippée, sinon aria-live reste muet.
      expect(balise).not.toContain('hidden');
      expect(balise).not.toContain('visually-hidden');
    },
  );

  it('les deux zones sont rendues vides (le message est posé côté client)', async () => {
    const html = await render();
    expect(html).toMatch(/<p[^>]*id="noresult"[^>]*>\s*<\/p>/);
    expect(html).toMatch(/<p[^>]*id="ep-noresult"[^>]*>\s*<\/p>/);
  });

  it('les cartes reco reçoivent le numéro d’épisode résolu par guid', async () => {
    collections([reco()], [episode({ guid: 'ep-1', number: 42 })]);
    const html = await render();
    expect(html).toContain('#42');
  });

  it('une reco orpheline (guid inconnu) ne casse pas le rendu', async () => {
    collections([reco({ episodeGuid: 'inconnu' })], [episode()]);
    const html = await render();
    expect(html).toContain('Parasite');
    expect(html).not.toContain('undefined');
  });
});
