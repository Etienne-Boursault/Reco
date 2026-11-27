/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/clicSortant.ts` (D1, R-1 et R-10, AU-2 B, 2026-11-27) :
 * le clic sur un lien d'œuvre envoie l'URL, la source et les trois oui/non de
 * la mesure du navigateur, sans jamais créer ni modifier cet état.
 *
 * Le `navigator`, le chemin et `fetch` sont injectés ; la mesure est la vraie,
 * sur le `localStorage` de happy-dom.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cablerClicSortant } from '../../src/utils/clicSortant';
import { creerMesure } from '../../src/utils/mesureNavigateur';

const CLE = 'reco.mesure';
const EPISODE = '/ubm/episode/abc';
const FICHE = '/ubm/oeuvre/film-x';

type Nav = { sendBeacon?: unknown; globalPrivacyControl?: boolean; doNotTrack?: string | null };

/** Une page avec un lien d'œuvre ; `pathname` est la page où l'on clique. */
function monde(pathname: string, nav: Nav = {}, jour = '2026-11-27') {
  document.head.innerHTML = '';
  document.body.innerHTML =
    '<a id="lien" href="https://www.themoviedb.org/movie/42" data-track="click" data-category="tmdb" data-source-id="ubm" data-reco-id="ubm-0001"><span id="dedans">TMDB</span></a>' +
    '<a id="autre" href="https://exemple.org/">autre</a>' +
    '<a id="sans-source" href="https://exemple.org/" data-track="click" data-category="tmdb">x</a>';
  const sendBeacon = vi.fn(() => true);
  const navigator = { sendBeacon, ...nav };
  const fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
  const mesure = creerMesure({
    stockage: () => localStorage,
    maintenant: () => new Date(`${jour}T12:00:00Z`),
    navigator,
  });
  const armé = cablerClicSortant({ navigator, document, location: { pathname }, fetch, mesure } as never);
  const clic = (id = 'lien') => document.getElementById(id)!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  const corps = async () => JSON.parse(await ((sendBeacon.mock.calls[0] as unknown[])[1] as Blob).text());
  return { armé, clic, sendBeacon, fetch, corps, navigator, mesure };
}

beforeEach(() => localStorage.clear());

describe('cablerClicSortant : ce qui part', () => {
  it('envoie l’URL, la source et les trois oui/non, sans rien écrire dans le stockage', async () => {
    // Un visiteur de la veille, qui a vu un épisode puis arrive sur une fiche.
    creerMesure({ stockage: () => localStorage, maintenant: () => new Date('2026-11-26T12:00:00Z'), navigator: {} }).noterPage(EPISODE);
    const avant = localStorage.getItem(CLE);
    const m = monde(FICHE);
    m.clic();
    expect(m.sendBeacon).toHaveBeenCalledTimes(1);
    expect(m.sendBeacon.mock.calls[0][0]).toBe('/api/click');
    expect(await m.corps()).toEqual({
      url: 'https://www.themoviedb.org/movie/42',
      category: 'tmdb',
      sourceId: 'ubm',
      recoId: 'ubm-0001',
      ref: FICHE,
      revenant: true,
      aVuEpisode: false,
      aVuFiche: true,
    });
    expect(localStorage.getItem(CLE)).toBe(avant);
  });

  it('compte le chemin épisode puis fiche vu le même jour', async () => {
    const mesure = creerMesure({ stockage: () => localStorage, maintenant: () => new Date('2026-11-27T12:00:00Z'), navigator: {} });
    mesure.noterPage(EPISODE);
    mesure.noterPage(FICHE);
    const m = monde(FICHE);
    m.clic();
    expect(await m.corps()).toMatchObject({ revenant: false, aVuEpisode: true, aVuFiche: true });
  });

  it('sans état gardé (première page) : le clic part sans oui/non et ne crée rien', async () => {
    const m = monde(FICHE);
    m.clic();
    const corps = await m.corps();
    expect(corps).not.toHaveProperty('revenant');
    expect(corps).not.toHaveProperty('aVuFiche');
    expect(localStorage.getItem(CLE)).toBeNull();
  });

  it('stockage indisponible : le clic part sans oui/non', async () => {
    const navigator = { sendBeacon: vi.fn(() => true) };
    const mesure = creerMesure({
      stockage: () => {
        throw new Error('coupé');
      },
      maintenant: () => new Date(),
      navigator,
    });
    document.body.innerHTML =
      '<a id="lien" href="https://exemple.org/" data-track="click" data-category="tmdb" data-source-id="ubm">x</a>';
    cablerClicSortant({ navigator, document, location: { pathname: FICHE }, fetch: vi.fn(), mesure } as never);
    document.getElementById('lien')!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    const corps = JSON.parse(await ((navigator.sendBeacon.mock.calls[0] as unknown[])[1] as Blob).text());
    expect(corps).toMatchObject({ url: 'https://exemple.org/', recoId: null });
    expect(corps).not.toHaveProperty('revenant');
  });

  it('un clic sur un élément à l’intérieur du lien compte aussi', () => {
    const m = monde(FICHE);
    m.clic('dedans');
    expect(m.sendBeacon).toHaveBeenCalledTimes(1);
  });

  it('un lien sans marque, ou sans source, n’envoie rien ; un clic hors lien non plus', () => {
    const m = monde(FICHE);
    m.clic('autre');
    m.clic('sans-source');
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    document.dispatchEvent(new MouseEvent('click'));
    expect(m.sendBeacon).not.toHaveBeenCalled();
  });

  it('replie sur fetch keepalive sans sendBeacon, et avale son rejet', () => {
    const m = monde(FICHE, { sendBeacon: undefined });
    m.fetch.mockReturnValueOnce(Promise.reject(new Error('réseau')));
    m.clic();
    const [url, init] = m.fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/click');
    expect(init).toMatchObject({ method: 'POST', keepalive: true });
  });

  it('une exception de l’envoi est avalée : le clic doit aboutir', () => {
    const m = monde(FICHE);
    m.sendBeacon.mockImplementation(() => {
      throw new Error('boum');
    });
    expect(() => m.clic()).not.toThrow();
  });
});

describe('cablerClicSortant : refus et pages écartées', () => {
  it.each([
    ['Global Privacy Control', { globalPrivacyControl: true }],
    ['Do Not Track à 1', { doNotTrack: '1' }],
  ])('%s : le clic n’envoie rien', (_nom, nav) => {
    const m = monde(FICHE, nav);
    m.clic();
    expect(m.sendBeacon).not.toHaveBeenCalled();
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('Do Not Track à 0 laisse passer', () => {
    const m = monde(FICHE, { doNotTrack: '0' });
    m.clic();
    expect(m.sendBeacon).toHaveBeenCalledTimes(1);
  });

  it('le refus de la personne est lu au moment du clic, pas au chargement', () => {
    const m = monde(FICHE);
    m.mesure.noterPage(FICHE);
    m.mesure.refuser();
    m.clic();
    expect(m.sendBeacon).not.toHaveBeenCalled();
  });

  it('GPC survenu après le chargement : le clic n’envoie rien non plus', () => {
    const m = monde(FICHE);
    (m.navigator as Nav).globalPrivacyControl = true;
    m.clic();
    expect(m.sendBeacon).not.toHaveBeenCalled();
  });

  it('/meta et pages noindex : rien n’est armé', () => {
    const m = monde('/meta/reseau');
    expect(m.armé).toBe(false);
    m.clic();
    expect(m.sendBeacon).not.toHaveBeenCalled();
  });
});
