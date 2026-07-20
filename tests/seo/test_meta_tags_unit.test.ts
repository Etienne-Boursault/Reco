/**
 * Tests unitaires `MetaTags.astro` via l'Astro Container API.
 *
 * Permet de valider le rendu HTML sans build complet (CR senior L11,
 * archi P3-E — justifie aussi la devDep `happy-dom`/vitest).
 *
 * NB : `experimental_AstroContainer` est en Astro 5+. Si la version de
 * `astro` change l'API, ce test fail et signale la migration.
 */

import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import MetaTags from '../../src/components/MetaTags.astro';

async function renderTags(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(MetaTags as any, { props });
}

describe('MetaTags (Container API)', () => {
  it('échappe </script> dans le JSON-LD (anti-XSS C2)', async () => {
    const html = await renderTags({
      title: 'X',
      description: 'd',
      canonicalUrl: 'https://x.fr/',
      socialImage: 'https://x.fr/og.png',
      jsonLd: { '@type': 'Test', payload: 'evil</script>' },
    });
    expect(html).not.toContain('evil</script>');
    expect(html).toContain('\\u003c/script');
  });

  it('appendSiteName par défaut ajoute le suffixe', async () => {
    const html = await renderTags({
      title: 'Mon titre',
      description: 'd',
      canonicalUrl: 'https://x.fr/',
      socialImage: 'https://x.fr/og.png',
    });
    expect(html).toContain('Mon titre — Reco');
  });

  it("n'ajoute pas le suffixe si déjà présent", async () => {
    const html = await renderTags({
      title: 'Accueil — Reco',
      description: 'd',
      canonicalUrl: 'https://x.fr/',
      socialImage: 'https://x.fr/og.png',
    });
    // Une seule occurrence de "— Reco" dans le <title>.
    const titleMatch = html.match(/<title>([^<]+)<\/title>/);
    expect(titleMatch?.[1]).toBe('Accueil — Reco');
  });

  it('twitter:site et twitter:creator émis si fournis', async () => {
    const html = await renderTags({
      title: 'X',
      description: 'd',
      canonicalUrl: 'https://x.fr/',
      socialImage: 'https://x.fr/og.png',
      twitterSite: '@reco',
      twitterCreator: '@author',
    });
    expect(html).toContain('name="twitter:site" content="@reco"');
    expect(html).toContain('name="twitter:creator" content="@author"');
  });

  it('alternates supplémentaires émis sans doubler fr/x-default', async () => {
    const html = await renderTags({
      title: 'X',
      description: 'd',
      canonicalUrl: 'https://x.fr/',
      socialImage: 'https://x.fr/og.png',
      alternates: [
        { hreflang: 'en', href: 'https://x.com/' },
        { hreflang: 'fr', href: 'https://dup/' }, // dédupliqué
      ],
    });
    expect(html).toContain('hreflang="en"');
    const frCount = (html.match(/hreflang="fr"/g) || []).length;
    expect(frCount).toBe(1);
  });
});
