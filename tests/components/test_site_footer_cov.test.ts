/**
 * Tests `SiteFooter.astro` — pied de page unifié (landmark contentinfo).
 *
 * Le footer lit la collection `sources` pour en extraire les liens
 * « Soutenir » de la source primaire (la première source activée). On mocke
 * `astro:content` pour piloter ce choix : source activée, source désactivée,
 * collection vide.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

const { experimental_AstroContainer: AstroContainer } = await import('astro/container');
const SiteFooter = (await import('../../src/components/SiteFooter.astro')).default;

async function render(
  props: Record<string, unknown> = {},
  slots: Record<string, unknown> = {},
): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(SiteFooter as any, { props, slots });
}

const KOFI = { platform: 'kofi', url: 'https://ko-fi.com/reco' };

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockResolvedValue([]);
});

describe('SiteFooter — structure', () => {
  it('rend un landmark contentinfo avec la nav secondaire', async () => {
    const html = await render();
    expect(html).toContain('role="contentinfo"');
    expect(html).toMatch(/<nav class="site-footer-nav"[^>]*aria-label="Liens secondaires"/);
    expect(html).toContain('href="/a-propos"');
    expect(html).toContain('href="/manifeste"');
  });

  it('tagline i18n par défaut', async () => {
    const html = await render();
    expect(html).toContain('Projet ouvert et duplicable — une source = un podcast.');
  });

  it('tagline personnalisée remplace celle par défaut', async () => {
    const html = await render({ tagline: 'Ma propre accroche' });
    expect(html).toContain('Ma propre accroche');
    expect(html).not.toContain('Projet ouvert et duplicable');
  });

  it('le slot est inséré avant les liens de soutien', async () => {
    getCollection.mockResolvedValue([{ data: { support: [KOFI] } }]);
    const html = await render({}, { default: '<p class="extra">Mention légale</p>' });
    expect(html.indexOf('Mention légale')).toBeGreaterThan(-1);
    expect(html.indexOf('Mention légale')).toBeLessThan(html.indexOf('support-list'));
  });
});

describe('SiteFooter — résolution de la source primaire', () => {
  it('collection vide → aucun lien de soutien, footer quand même rendu', async () => {
    const html = await render();
    expect(html).toContain('role="contentinfo"');
    expect(html).not.toContain('support-list');
  });

  it('prend la première source activée pour les liens de soutien', async () => {
    getCollection.mockResolvedValue([
      { data: { enabled: false, support: [{ platform: 'paypal', url: 'https://paypal.me/off' }] } },
      { data: { enabled: true, support: [KOFI] } },
    ]);
    const html = await render();
    expect(html).toContain('https://ko-fi.com/reco');
    expect(html).not.toContain('paypal.me/off');
  });

  it('toutes les sources désactivées → repli sur la première de la collection', async () => {
    getCollection.mockResolvedValue([
      { data: { enabled: false, support: [KOFI] } },
      { data: { enabled: false, support: [] } },
    ]);
    const html = await render();
    expect(html).toContain('https://ko-fi.com/reco');
  });

  it('source primaire sans champ support → aucun bloc de soutien', async () => {
    getCollection.mockResolvedValue([{ data: { enabled: true } }]);
    const html = await render();
    expect(html).not.toContain('support-list');
  });

  it('une source sans champ enabled est considérée comme activée', async () => {
    getCollection.mockResolvedValue([{ data: { support: [KOFI] } }]);
    const html = await render();
    expect(html).toContain('https://ko-fi.com/reco');
  });
});
