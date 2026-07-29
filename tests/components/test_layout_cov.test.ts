/**
 * Tests de rendu `src/layouts/Layout.astro` via l'Astro Container API.
 *
 * Layout est le squelette de TOUTES les pages publiques : `<html lang>`,
 * variables CSS de thème injectées par source, résolution de l'image OG
 * (explicite → carte Satori → repli statique), skip-link, `<noscript>`,
 * footer optionnel. On couvre ici chaque branche du frontmatter.
 *
 * `astro:content` est mocké à la frontière : `SiteFooter` (monté par le
 * layout) lit la collection `sources` pour ses liens « Soutenir ».
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

const { renderWithSite } = await import('./_container');
const Layout = (await import('../../src/layouts/Layout.astro')).default;

async function render(
  props: Record<string, unknown>,
  slot = '<main id="main">contenu</main>',
): Promise<string> {
  return renderWithSite(Layout, { props, slots: { default: slot } });
}

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockResolvedValue([]);
});

const THEME = {
  colors: {
    bg: '#101014',
    surface: '#1b1b22',
    text: '#f6f4ee',
    muted: '#9a9aa2',
    accent: '#ffd23f',
  },
};

describe('Layout — squelette de page', () => {
  it('rend le document HTML avec la langue par défaut et le slot', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html.startsWith('<html lang="fr"')).toBe(true);
    expect(html).toContain('<main id="main">contenu</main>');
    expect(html.trimEnd().endsWith('</html>')).toBe(true);
  });

  it('expose le skip-link WCAG 2.4.1 vers #main', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toMatch(
      /<a href="#main" class="skip-link"[^>]*>Aller au contenu principal<\/a>/,
    );
  });

  it('rend le message <noscript> informatif', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toMatch(/<noscript>[\s\S]*noscript-warning/);
  });

  it('monte la palette de recherche globale (disponible sur toute page)', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toContain('data-search-palette');
  });
});

describe('Layout — description', () => {
  it('utilise la description par défaut quand la prop est absente', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toContain('Recommandations d’œuvres mentionnées dans des podcasts.');
  });

  it('utilise la description fournie quand elle existe', async () => {
    const html = await render({ title: 'Ma page', description: 'Ma description à moi' });
    expect(html).toContain('Ma description à moi');
    expect(html).not.toContain('Recommandations d’œuvres mentionnées dans des podcasts.');
  });
});

describe('Layout — image de partage (ADR 0021)', () => {
  it('sans ogImage ni ogSlug → repli statique /og/default.png', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toContain('content="https://reco.test/og/default.png"');
  });

  it('ogSlug → carte Satori /og/<slug>.png', async () => {
    const html = await render({ title: 'Ma page', ogSlug: 'ubm' });
    expect(html).toContain('content="https://reco.test/og/ubm.png"');
  });

  it('ogImage explicite prime sur ogSlug', async () => {
    const html = await render({
      title: 'Ma page',
      ogSlug: 'ubm',
      ogImage: 'https://i.ytimg.com/vi/abc/maxres.jpg',
    });
    expect(html).toContain('content="https://i.ytimg.com/vi/abc/maxres.jpg"');
    expect(html).not.toContain('/og/ubm.png');
  });
});

describe('Layout — canonical & ogType', () => {
  it("l'URL canonique combine Astro.site et le pathname courant", async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toMatch(/<link rel="canonical" href="https:\/\/reco\.test\//);
  });

  it('ogType vaut website par défaut', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toContain('property="og:type" content="website"');
  });

  it('ogType=article est transmis à MetaTags', async () => {
    const html = await render({ title: 'Ma page', ogType: 'article' });
    expect(html).toContain('property="og:type" content="article"');
  });
});

describe('Layout — noindex', () => {
  it('aucune balise robots par défaut', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).not.toContain('name="robots"');
  });

  it('noindex=true → <meta name="robots" content="noindex, nofollow">', async () => {
    const html = await render({ title: 'Ma page', noindex: true });
    expect(html).toContain('<meta name="robots" content="noindex, nofollow">');
  });
});

describe('Layout — thème de source (multi-podcast)', () => {
  it('sans thème : aucun style inline sur <html> et theme-color de repli', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).not.toContain('--accent:');
    expect(html).toContain('name="theme-color" content="#0e0e10"');
  });

  it('avec thème : injecte les 6 variables CSS sur <html>', async () => {
    const html = await render({ title: 'Ma page', theme: THEME });
    expect(html).toContain('--bg:#101014');
    expect(html).toContain('--surface:#1b1b22');
    expect(html).toContain('--text:#f6f4ee');
    expect(html).toContain('--muted:#9a9aa2');
    expect(html).toContain('--accent:#ffd23f');
  });

  it('accentText absent → repli #0e0e10', async () => {
    const html = await render({ title: 'Ma page', theme: THEME });
    expect(html).toContain('--accent-text:#0e0e10');
  });

  it('accentText fourni → utilisé tel quel', async () => {
    const html = await render({
      title: 'Ma page',
      theme: { colors: { ...THEME.colors, accentText: '#123456' } },
    });
    expect(html).toContain('--accent-text:#123456');
  });

  it('theme-color mobile suit la couleur de fond du thème', async () => {
    const html = await render({ title: 'Ma page', theme: THEME });
    expect(html).toContain('name="theme-color" content="#101014"');
  });

  it('theme sans bloc colors → repli #0e0e10 et pas de variables', async () => {
    const html = await render({ title: 'Ma page', theme: { fontBody: 'Inter' } });
    expect(html).toContain('name="theme-color" content="#0e0e10"');
    expect(html).not.toContain('--accent:');
  });
});

describe('Layout — footer', () => {
  it('monte le SiteFooter par défaut', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).toContain('role="contentinfo"');
  });

  it('showFooter=false → aucun footer (page interne à footer propre)', async () => {
    const html = await render({ title: 'Ma page', showFooter: false });
    expect(html).not.toContain('role="contentinfo"');
  });
});

describe('Layout — JSON-LD', () => {
  it('sans jsonLd, aucun bloc ld+json', async () => {
    const html = await render({ title: 'Ma page' });
    expect(html).not.toContain('application/ld+json');
  });

  it('avec jsonLd, le bloc schema.org est embarqué dans <head>', async () => {
    const html = await render({
      title: 'Ma page',
      jsonLd: { '@context': 'https://schema.org', '@type': 'WebSite', name: 'Reco' },
    });
    expect(html).toContain('application/ld+json');
    expect(html).toContain('"@type":"WebSite"');
  });
});

describe('Layout — locale', () => {
  it('lang explicite est posé sur <html> et pilote les chaînes i18n', async () => {
    const html = await render({ title: 'Ma page', lang: 'fr' });
    expect(html).toContain('<html lang="fr"');
    expect(html).toContain('Aller au contenu principal');
  });
});
