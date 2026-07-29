/**
 * Branches restantes de `MetaTags.astro`.
 *
 * Le composant accepte indifféremment des `URL` ou des chaînes pour l'URL
 * canonique et l'image sociale (Layout passe des `URL`, d'autres appelants
 * des chaînes déjà résolues) : les deux formes doivent produire le même
 * balisage. On couvre aussi les balises conditionnelles (`theme-color`,
 * `robots`, comptes Twitter) et la déduplication des `hreflang`.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import MetaTags from '../../src/components/MetaTags.astro';

const BASE = {
  title: 'Une page',
  description: 'Une description',
  canonicalUrl: 'https://reco.test/page',
  socialImage: 'https://reco.test/og/page.png',
};

async function render(props: Record<string, unknown> = {}): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(MetaTags as any, { props: { ...BASE, ...props } });
}

describe('MetaTags — URL en objet ou en chaîne', () => {
  it('canonicalUrl fourni en chaîne est rendu tel quel', async () => {
    const html = await render();
    expect(html).toContain('<link rel="canonical" href="https://reco.test/page">');
  });

  it('canonicalUrl fourni en objet URL est sérialisé', async () => {
    const html = await render({ canonicalUrl: new URL('https://reco.test/page') });
    expect(html).toContain('<link rel="canonical" href="https://reco.test/page">');
  });

  it('socialImage en chaîne et en objet URL donnent la même balise og:image', async () => {
    const chaine = await render();
    const objet = await render({ socialImage: new URL('https://reco.test/og/page.png') });
    expect(chaine).toContain('property="og:image" content="https://reco.test/og/page.png"');
    expect(objet).toContain('property="og:image" content="https://reco.test/og/page.png"');
  });

  it('les deux formes produisent un balisage identique', async () => {
    const chaine = await render();
    const objet = await render({
      canonicalUrl: new URL('https://reco.test/page'),
      socialImage: new URL('https://reco.test/og/page.png'),
    });
    expect(objet).toBe(chaine);
  });
});

describe('MetaTags — balises conditionnelles', () => {
  it('sans themeColor, aucune balise theme-color', async () => {
    const html = await render();
    expect(html).not.toContain('name="theme-color"');
  });

  it('avec themeColor, la balise est émise', async () => {
    const html = await render({ themeColor: '#101014' });
    expect(html).toContain('<meta name="theme-color" content="#101014">');
  });

  it('noindex=false (défaut) → aucune balise robots', async () => {
    const html = await render();
    expect(html).not.toContain('name="robots"');
  });

  it('noindex=true → robots noindex, nofollow', async () => {
    const html = await render({ noindex: true });
    expect(html).toContain('<meta name="robots" content="noindex, nofollow">');
  });

  it('sans comptes Twitter, aucune balise twitter:site/creator', async () => {
    const html = await render();
    expect(html).not.toContain('name="twitter:site"');
    expect(html).not.toContain('name="twitter:creator"');
  });

  it('avec comptes Twitter, les deux balises sont émises', async () => {
    const html = await render({ twitterSite: '@reco', twitterCreator: '@auteur' });
    expect(html).toContain('<meta name="twitter:site" content="@reco">');
    expect(html).toContain('<meta name="twitter:creator" content="@auteur">');
  });

  it('sans jsonLd, aucun bloc ld+json', async () => {
    const html = await render();
    expect(html).not.toContain('application/ld+json');
  });
});

describe('MetaTags — suffixe de titre', () => {
  it('ajoute « — Reco » par défaut', async () => {
    const html = await render();
    expect(html).toContain('<title>Une page — Reco</title>');
  });

  it('n’ajoute pas le suffixe s’il est déjà présent', async () => {
    const html = await render({ title: 'Une page — Reco' });
    expect(html).toContain('<title>Une page — Reco</title>');
  });

  it('appendSiteName=false force l’absence de suffixe', async () => {
    const html = await render({ appendSiteName: false });
    expect(html).toContain('<title>Une page</title>');
  });

  it('appendSiteName=true force l’ajout même si déjà suffixé', async () => {
    const html = await render({ title: 'Une page — Reco', appendSiteName: true });
    expect(html).toContain('<title>Une page — Reco — Reco</title>');
  });

  it('siteName personnalisé change suffixe et og:site_name', async () => {
    const html = await render({ siteName: 'MonFork' });
    expect(html).toContain('<title>Une page — MonFork</title>');
    expect(html).toContain('property="og:site_name" content="MonFork"');
  });
});

describe('MetaTags — hreflang', () => {
  it('émet fr et x-default par défaut', async () => {
    const html = await render();
    expect(html).toContain('hreflang="fr"');
    expect(html).toContain('hreflang="x-default"');
  });

  it('une alternance « fr » supplémentaire est dédupliquée', async () => {
    const html = await render({
      alternates: [{ hreflang: 'fr', href: 'https://autre.test/' }],
    });
    expect(html).not.toContain('https://autre.test/');
    expect((html.match(/hreflang="fr"/g) ?? []).length).toBe(1);
  });

  it('une alternance inédite est ajoutée', async () => {
    const html = await render({
      alternates: [{ hreflang: 'en', href: 'https://reco.test/en/page' }],
    });
    expect(html).toContain('<link rel="alternate" hreflang="en" href="https://reco.test/en/page">');
  });

  it('deux alternances identiques ne sont émises qu’une fois', async () => {
    const html = await render({
      alternates: [
        { hreflang: 'en', href: 'https://reco.test/en/page' },
        { hreflang: 'en', href: 'https://doublon.test/' },
      ],
    });
    expect((html.match(/hreflang="en"/g) ?? []).length).toBe(1);
    expect(html).not.toContain('doublon.test');
  });
});

describe('MetaTags — Open Graph', () => {
  it('ogType et ogLocale par défaut', async () => {
    const html = await render();
    expect(html).toContain('property="og:type" content="website"');
    expect(html).toContain('property="og:locale" content="fr_FR"');
  });

  it('ogType et ogLocale personnalisables', async () => {
    const html = await render({ ogType: 'article', ogLocale: 'en_US' });
    expect(html).toContain('property="og:type" content="article"');
    expect(html).toContain('property="og:locale" content="en_US"');
  });
});
