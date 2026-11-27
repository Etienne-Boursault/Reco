/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/signalVue.ts` (AU-1 A, 2026-11-27) : le signal « page
 * vue » envoyé par le navigateur, une fois par document.
 *
 * Les dépendances du navigateur sont injectées : aucun test ne touche au
 * vrai `navigator`, ni au réseau.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cablerSignalVue, pageMesurable } from '../../src/utils/signalVue';

type Option = Record<string, unknown>;

/** Un « navigateur » de poche : chaque test en règle les détails. */
function monde(options: Option = {}) {
  const document = Object.assign(new EventTarget(), {
    visibilityState: 'visible',
    prerendering: false,
    querySelector: () => null as unknown,
  });
  const window = new EventTarget();
  const navigator = {
    sendBeacon: vi.fn(() => true) as unknown,
    webdriver: false,
    globalPrivacyControl: false,
    doNotTrack: null as string | null,
  };
  const fetch = vi.fn(() => Promise.resolve(new Response(null, { status: 204 })));
  const deps = {
    navigator,
    document,
    window,
    location: { pathname: '/a-propos' },
    fetch,
  };
  Object.assign(deps.navigator, options.navigator);
  Object.assign(deps.document, options.document);
  if (options.location) deps.location = options.location as never;
  if (options.fetch) deps.fetch = options.fetch as never;
  return { deps: deps as never, navigator, document, window, fetch };
}

const balises = (m: ReturnType<typeof monde>) => m.navigator.sendBeacon as ReturnType<typeof vi.fn>;
const appels = (m: ReturnType<typeof monde>) => {
  const b = m.navigator.sendBeacon;
  return (vi.isMockFunction(b) ? b.mock.calls.length : 0) + m.fetch.mock.calls.length;
};

describe('cablerSignalVue : envoi', () => {
  it('envoie le chemin en JSON par sendBeacon, une fois la page visible', () => {
    const m = monde();
    expect(cablerSignalVue(m.deps)).toBe(true);
    expect(balises(m)).toHaveBeenCalledTimes(1);
    expect(balises(m)).toHaveBeenCalledWith('/api/vue', JSON.stringify({ chemin: '/a-propos' }));
    expect(m.fetch).not.toHaveBeenCalled();
  });

  it('ne renvoie rien sur un retour par le cache avant-arrière', () => {
    const m = monde();
    cablerSignalVue(m.deps);
    m.window.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    m.document.dispatchEvent(new Event('visibilitychange'));
    expect(appels(m)).toBe(1);
  });

  it('replie sur fetch keepalive quand sendBeacon est absent', () => {
    const m = monde({ navigator: { sendBeacon: undefined } });
    cablerSignalVue(m.deps);
    expect(m.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = m.fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/vue');
    expect(init).toMatchObject({
      method: 'POST',
      keepalive: true,
      body: JSON.stringify({ chemin: '/a-propos' }),
    });
  });

  it('replie sur fetch quand sendBeacon rend false', () => {
    const m = monde({ navigator: { sendBeacon: vi.fn(() => false) } });
    cablerSignalVue(m.deps);
    expect(m.fetch).toHaveBeenCalledTimes(1);
  });

  it('avale une erreur de fetch (rejet) sans bruit', async () => {
    const rejet = vi.fn(() => Promise.reject(new Error('hors ligne')));
    const m = monde({ navigator: { sendBeacon: undefined }, fetch: rejet });
    const nonGeree = vi.fn();
    process.on('unhandledRejection', nonGeree);
    expect(() => cablerSignalVue(m.deps)).not.toThrow();
    await new Promise((r) => setTimeout(r, 0));
    process.off('unhandledRejection', nonGeree);
    expect(rejet).toHaveBeenCalledTimes(1);
    expect(nonGeree).not.toHaveBeenCalled();
  });

  it('avale une exception levée par sendBeacon', () => {
    const m = monde({
      navigator: {
        sendBeacon: () => {
          throw new Error('refusé');
        },
      },
    });
    expect(() => cablerSignalVue(m.deps)).not.toThrow();
  });
});

describe('cablerSignalVue : quand envoyer', () => {
  it('attend que la page devienne visible', () => {
    const m = monde({ document: { visibilityState: 'hidden' } });
    cablerSignalVue(m.deps);
    expect(appels(m)).toBe(0);
    m.document.dispatchEvent(new Event('visibilitychange')); // toujours cachée
    expect(appels(m)).toBe(0);
    m.document.visibilityState = 'visible';
    m.document.dispatchEvent(new Event('visibilitychange'));
    m.document.dispatchEvent(new Event('visibilitychange'));
    expect(appels(m)).toBe(1);
  });

  it('attend la fin du prérendu, puis envoie', () => {
    const m = monde({ document: { prerendering: true } });
    cablerSignalVue(m.deps);
    expect(appels(m)).toBe(0);
    m.document.prerendering = false;
    m.document.dispatchEvent(new Event('prerenderingchange'));
    expect(appels(m)).toBe(1);
  });

  it('un document préchargé et caché attend encore sa visibilité', () => {
    const m = monde({ document: { prerendering: true, visibilityState: 'hidden' } });
    cablerSignalVue(m.deps);
    m.document.prerendering = false;
    m.document.dispatchEvent(new Event('prerenderingchange'));
    expect(appels(m)).toBe(0);
    m.document.visibilityState = 'visible';
    m.document.dispatchEvent(new Event('visibilitychange'));
    expect(appels(m)).toBe(1);
  });
});

describe('cablerSignalVue : refus', () => {
  it('navigator.webdriver coupe le signal', () => {
    const m = monde({ navigator: { webdriver: true } });
    expect(cablerSignalVue(m.deps)).toBe(false);
    expect(appels(m)).toBe(0);
  });

  it('Global Privacy Control coupe le signal', () => {
    const m = monde({ navigator: { globalPrivacyControl: true } });
    expect(cablerSignalVue(m.deps)).toBe(false);
    expect(appels(m)).toBe(0);
  });

  it('Do Not Track à « 1 » coupe le signal', () => {
    const m = monde({ navigator: { doNotTrack: '1' } });
    expect(cablerSignalVue(m.deps)).toBe(false);
    expect(appels(m)).toBe(0);
  });

  it('Do Not Track à « 0 » laisse passer', () => {
    const m = monde({ navigator: { doNotTrack: '0' } });
    expect(cablerSignalVue(m.deps)).toBe(true);
  });

  it('rien sur /meta ni sur une page noindex', () => {
    const m = monde({ location: { pathname: '/meta/annuaire' } });
    expect(cablerSignalVue(m.deps)).toBe(false);
    const n = monde({
      document: { querySelector: () => ({ getAttribute: () => 'noindex, nofollow' }) },
    });
    expect(cablerSignalVue(n.deps)).toBe(false);
    expect(appels(m) + appels(n)).toBe(0);
  });
});

describe('pageMesurable : la garde commune au signal et au clic', () => {
  beforeEach(() => {
    document.head.innerHTML = '';
  });
  const avec = (contenu: string | null, chemin = '/une-page') => {
    document.head.innerHTML = contenu === null ? '' : `<meta name="robots" content="${contenu}">`;
    return pageMesurable({ pathname: chemin }, document);
  };

  it('écarte /meta et ses sous-chemins, pas /metaphore', () => {
    expect(avec(null, '/meta')).toBe(false);
    expect(avec(null, '/meta/x')).toBe(false);
    expect(avec(null, '/metaphore')).toBe(true);
  });

  it('écarte noindex sous ses trois formes, pas une autre valeur', () => {
    expect(avec('noindex')).toBe(false);
    expect(avec('NoIndex, nofollow')).toBe(false);
    expect(avec('noindex nofollow')).toBe(false);
    expect(avec('index, follow')).toBe(true);
    expect(avec(null)).toBe(true);
  });

  it('une balise robots sans content laisse passer', () => {
    document.head.innerHTML = '<meta name="robots">';
    expect(pageMesurable({ pathname: '/p' }, document)).toBe(true);
  });
});
