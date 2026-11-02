/**
 * Composants des listes : bandeau des pages par type, ligne d'épisode,
 * cartes de la page, carte de l'onglet « Par type », lien du pied de page,
 * et la page `/[source]/listes` elle-même.
 *
 * `astro:content` est mocké. Les listes viennent soit d'une prop (cas
 * limites), soit du dépôt réel pour `un-bon-moment` (cas nominal).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

const { experimental_AstroContainer: AstroContainer } = await import('astro/container');
const ListesBandeau = (await import('../../src/components/ListesBandeau.astro')).default;
const ListesEpisode = (await import('../../src/components/ListesEpisode.astro')).default;
const ListesCarteMusique = (await import('../../src/components/ListesCarteMusique.astro')).default;
const ListesCarteSensCritique = (await import('../../src/components/ListesCarteSensCritique.astro')).default;
const GalleryIndex = (await import('../../src/components/GalleryIndex.astro')).default;
const SiteFooter = (await import('../../src/components/SiteFooter.astro')).default;
const WorkCard = (await import('../../src/components/WorkCard.astro')).default;
const { renderPage, visibleText } = await import('../gallery/_render_page');
const PageListes = (await import('../../src/pages/[source]/listes.astro')).default;
const pageListes = await import('../../src/pages/[source]/listes.astro');
import type { Listes, Playlist } from '../../src/lib/listes/donnees';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function rendre(Composant: any, props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(Composant, { props });
}

const pl = (saison: number | null, n = 3): Playlist => ({
  nom: saison ? `Saison ${saison}` : 'Toutes les recos musicales',
  saison,
  spotify: `https://open.spotify.com/playlist/s${saison ?? 'T'}`,
  deezer: `https://www.deezer.com/fr/playlist/${saison ?? 0}`,
  titres: { spotify: n, deezer: n },
});
const sc = (genre: 'film' | 'serie' | 'livre' | 'bd', n: number) => ({
  genre,
  url: `https://www.senscritique.com/liste/${genre}/1`,
  oeuvres: Array.from({ length: n }, (_, i) => `${genre}${i}`),
});
const LISTES: Listes = {
  toutes: pl(null, 298),
  saisons: [pl(6, 18), pl(5, 85)],
  senscritique: [sc('film', 122), sc('serie', 5), sc('livre', 51), sc('bd', 14)],
};
const ITEM = { id: 'abc', title: 'Marie Jay', types: ['artiste'], creator: null };

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockResolvedValue([]);
});

describe('ListesBandeau', () => {
  it('musique : playlist cumulée, nombre réel, lien vers les saisons', async () => {
    const html = await rendre(ListesBandeau, { sourceId: 'un-bon-moment', genres: 'musique' });
    const brut = JSON.parse(readFileSync('tools/data/playlists_spotify.json', 'utf-8'));
    const n = brut.playlists['Toutes les recos musicales'].titres.length;
    expect(visibleText(html)).toContain(`À écouter d’une traite : ${n} titres en playlist`);
    expect(html).toContain('aria-label="Écouter la playlist « Toutes les recos musicales » sur Spotify (nouvel onglet)"');
    expect(html).toContain('href="/un-bon-moment/listes"');
    expect(html).not.toMatch(/<iframe|<img|<script/);
  });

  it('films : une liste, une phrase qui ne prétend pas tout contenir', async () => {
    const html = await rendre(ListesBandeau, { sourceId: 'x', genres: ['film'], listes: LISTES });
    expect(visibleText(html)).toContain('rassemble 122 des films recommandés ici. Voir la liste ↗ Toutes les listes →');
    expect(html).toContain('href="https://www.senscritique.com/liste/film/1"');
  });

  it('livres : deux listes, deux boutons nommés', async () => {
    const html = await rendre(ListesBandeau, { sourceId: 'x', genres: ['livre', 'bd'], listes: LISTES });
    expect(visibleText(html)).toContain('51 des livres et 14 des BD recommandés ici. Liste des livres ↗ Liste des BD ↗');
    expect(html).toContain('aria-label="Voir la liste SensCritique des BD (nouvel onglet)"');
  });

  it('rien sans listes, sans la liste du genre, ou sans playlist cumulée', async () => {
    expect(await rendre(ListesBandeau, { sourceId: 'autre', genres: 'musique' })).not.toContain('lst-bandeau');
    expect(await rendre(ListesBandeau, { sourceId: 'x', genres: ['film'], listes: null })).not.toContain('lst-bandeau');
    const sansFilm = { ...LISTES, toutes: null, senscritique: [sc('bd', 1)] };
    expect(await rendre(ListesBandeau, { sourceId: 'x', genres: ['film'], listes: sansFilm })).not.toContain('lst-bandeau');
    expect(await rendre(ListesBandeau, { sourceId: 'x', genres: 'musique', listes: sansFilm })).not.toContain('lst-bandeau');
  });
});

describe('ListesEpisode', () => {
  function corpus(liens: { url: string }[]) {
    getCollection.mockImplementation(async (nom: string) => ({
      items: [{ id: 'src/m', data: { id: 'm', title: 'M', types: ['musique'] } }, { id: 'autre/z', data: { id: 'z', title: 'Z', types: ['musique'] } }],
      mentions: [
        { data: { id: 'r', itemId: 'm', status: 'validated', kind: 'reco', sourceRef: { sourceId: 'src', episodeGuid: 'ep1' } } },
        { data: { id: 'q', itemId: 'z', status: 'validated', kind: 'reco', sourceRef: { sourceId: 'autre', episodeGuid: 'ep1' } } },
      ],
      recos: [{ data: { id: 'r', sourceId: { id: 'src' }, links: liens } }, { data: { id: 'q', sourceId: { id: 'autre' }, links: liens } }],
    })[nom] ?? []);
  }

  it('épisode musical : la playlist de sa saison, en fin de page', async () => {
    corpus([{ url: 'https://open.spotify.com/track/1' }]);
    const html = await rendre(ListesEpisode, { sourceId: 'src', episodeGuid: 'ep1', season: 6, listes: LISTES });
    expect(visibleText(html)).toContain('La musique de cet épisode est dans la playlist Saison 6 : Spotify ↗ Deezer ↗ Toutes les listes →');
    expect(html).toContain('href="https://www.deezer.com/fr/playlist/6"');
  });

  it('hors-série sans saison : la playlist qui cumule tout', async () => {
    corpus([{ url: 'https://open.spotify.com/track/1' }]);
    const html = await rendre(ListesEpisode, { sourceId: 'src', episodeGuid: 'ep1', listes: LISTES });
    expect(visibleText(html)).toContain('dans la playlist Toutes les recos musicales :');
  });

  it('aucune ligne sans reco musicale entrée en playlist, ni sans listes', async () => {
    corpus([{ url: 'https://www.deezer.com/track/1' }]);
    expect(await rendre(ListesEpisode, { sourceId: 'src', episodeGuid: 'ep1', season: 6, listes: LISTES })).not.toContain('lst-episode');
    expect(await rendre(ListesEpisode, { sourceId: 'src', episodeGuid: 'ep1', season: 6, listes: null })).not.toContain('lst-episode');
    expect(await rendre(ListesEpisode, { sourceId: 'autre-source', episodeGuid: 'ep1' })).not.toContain('lst-episode');
  });
});

describe('Cartes de la page', () => {
  it('carte musique complète', async () => {
    const html = await rendre(ListesCarteMusique, {
      sourceId: 'src',
      toutes: LISTES.toutes,
      saisons: LISTES.saisons,
      ajouts: [{ item: ITEM, detail: 'S6·E7' }],
    });
    const texte = visibleText(html);
    expect(texte).toContain('Toutes les recos musicales 298 titres sur Spotify et Deezer');
    expect(texte).toContain('Marie Jay S6·E7');
    expect(texte).toContain('Par saison S6 Saison 6 · 18 titres Spotify Deezer');
    expect(html).toContain('href="/src/oeuvre/abc"');
    expect(html).toContain('aria-label="Écouter la playlist « Saison 5 » sur Deezer (nouvel onglet)"');
  });

  it('carte musique sans playlist cumulée ni ajouts', async () => {
    const html = await rendre(ListesCarteMusique, { sourceId: 'src', toutes: null, saisons: [pl(2)], ajouts: [] });
    expect(html).toMatch(/<h2[^>]*>Par saison<\/h2>/);
    expect(html).not.toContain('Derniers ajouts');
  });

  it('carte musique sans saisons', async () => {
    const html = await rendre(ListesCarteMusique, { sourceId: 'src', toutes: LISTES.toutes, saisons: [], ajouts: [] });
    expect(html).not.toContain('Par saison');
  });

  it('carte SensCritique', async () => {
    const avec = await rendre(ListesCarteSensCritique, { sourceId: 'src', liste: sc('bd', 14), ajouts: [{ item: ITEM, detail: '' }] });
    expect(visibleText(avec)).toContain('Bandes dessinées 14 œuvres sur SensCritique Voir la liste ↗ Derniers ajouts');
    const sans = await rendre(ListesCarteSensCritique, { sourceId: 'src', liste: sc('film', 1), ajouts: [] });
    expect(visibleText(sans)).toContain('1 œuvre sur SensCritique');
    expect(sans).not.toContain('Derniers ajouts');
  });

  it('WorkCard : le détail remplace l’année', async () => {
    const html = await rendre(WorkCard, { sourceId: 'src', item: { ...ITEM, year: 1999 }, detail: 'S6·E7' });
    expect(html).toContain('S6·E7');
    expect(html).not.toContain('1999');
  });
});

describe('Accès depuis l’accueil et le pied de page', () => {
  it('« Par type » : la carte des listes vient après les galeries', async () => {
    const galeries = [{ slug: 'films', court: 'Films', types: ['film'], titre: 'Tous les films', unGe: '', plusieurs: '', vide: '', n: 3, apercu: ['A'] }];
    const html = await rendre(GalleryIndex, { sourceId: 'un-bon-moment', galeries });
    expect(html.indexOf('/un-bon-moment/films')).toBeLessThan(html.indexOf('/un-bon-moment/listes'));
    expect(visibleText(html)).toMatch(/\d+ listes Listes et playlists Toutes les recos musicales · \d+ titres Une playlist par saison Films, séries, livres et BD sur SensCritique Voir les listes →/);
    const ailleurs = await rendre(GalleryIndex, { sourceId: 'autre', galeries });
    expect(ailleurs).not.toContain('/listes');
  });

  it('pied de page : le lien n’existe que pour une source qui a des listes', async () => {
    getCollection.mockResolvedValue([{ id: 'un-bon-moment', data: {} }]);
    const avec = await rendre(SiteFooter, {});
    expect(avec).toContain('href="/un-bon-moment/listes"');
    expect(avec.indexOf('/stats')).toBeLessThan(avec.indexOf('/un-bon-moment/listes'));
    getCollection.mockResolvedValue([{ id: 'autre', data: {} }]);
    expect(await rendre(SiteFooter, {})).not.toContain('/listes');
  });
});

describe('Page /[source]/listes', () => {
  const SOURCE = (id: string) => ({
    id,
    data: { id, title: 'Un Bon Moment', theme: { colors: { bg: '#000', surface: '#111', text: '#fff', muted: '#999', accent: '#fc0' } } },
  });

  it('n’est générée que pour une source qui a des listes', async () => {
    getCollection.mockResolvedValue([SOURCE('un-bon-moment'), SOURCE('autre')]);
    const chemins = (await pageListes.getStaticPaths()) as { params: { source: string } }[];
    expect(chemins.map((c) => c.params.source)).toEqual(['un-bon-moment']);
  });

  it('rend les cartes, les derniers ajouts et les métadonnées', async () => {
    getCollection.mockImplementation(async (nom: string) => ({
      items: [{ id: 'src/m', data: { id: 'm', title: 'Morceau', types: ['musique'] } }, { id: 'src/f', data: { id: 'f', title: 'Le Film', types: ['film'], creator: 'X' } }],
      mentions: [
        { data: { id: 'r', itemId: 'm', status: 'validated', kind: 'reco', sourceRef: { sourceId: 'src', episodeGuid: 'e' } } },
        { data: { id: 's', itemId: 'f', status: 'validated', kind: 'reco', sourceRef: { sourceId: 'src', episodeGuid: 'e' } } },
      ],
      recos: [{ data: { id: 'r', sourceId: { id: 'src' }, links: [{ url: 'https://open.spotify.com/track/1' }] } }],
      episodes: [{ data: { guid: 'e', sourceId: { id: 'src' }, season: 6, number: 7, date: new Date('2026-10-30') } }],
    })[nom] ?? []);
    const listes = { ...LISTES, senscritique: [{ ...sc('film', 1), oeuvres: ['f'] }] };
    const html = await renderPage(PageListes, { params: { source: 'src' }, props: { source: SOURCE('src'), listes }, path: '/src/listes' });
    const texte = visibleText(html);
    expect(html).toMatch(/<h1[^>]*>Listes et playlists<\/h1>/);
    expect(texte).toContain('Les recos du podcast Un Bon Moment , rangées dans des playlists');
    expect(texte).toContain('Morceau S6·E7');
    expect(texte).toContain('Films 1 œuvre sur SensCritique Voir la liste ↗ Derniers ajouts Film Le Film X S6·E7');
    expect(html).toContain('<title>Listes et playlists — Un Bon Moment');
    expect(html).toContain('/src/listes');
  });

  it('sans playlist ni liste SensCritique, aucune carte vide', async () => {
    const html = await renderPage(PageListes, {
      params: { source: 'src' },
      props: { source: SOURCE('src'), listes: { toutes: null, saisons: [], senscritique: [] } },
      path: '/src/listes',
    });
    expect(html).not.toContain('lst-bloc');
  });
});
