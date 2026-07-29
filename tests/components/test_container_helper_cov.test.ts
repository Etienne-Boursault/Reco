/**
 * Tests du helper `tests/components/_container.ts`.
 *
 * Ce helper est le point d'appui de tous les tests de `Layout.astro` et
 * `SourceCatalog.astro` : s'il cesse d'injecter `Astro.site`, ce sont des
 * dizaines de tests qui tombent d'un bloc avec un `TypeError: Invalid URL`
 * illisible. On verrouille donc ici son CONTRAT, pas son implémentation —
 * de sorte qu'une montée de version d'Astro qui rendrait la voie publique
 * fonctionnelle laisse ces tests verts.
 */
import { describe, it, expect } from 'vitest';
import { renderWithSite, voieUtilisee, TEST_SITE } from './_container';
import SiteProbe from './_site_probe.astro';

describe('_container — injection de Astro.site', () => {
  it('un composant rendu voit une URL de site absolue', async () => {
    const html = await renderWithSite(SiteProbe);
    const site = html.match(/data-site="([^"]*)"/)?.[1] ?? '';
    expect(site).not.toBe('');
    expect(() => new URL(site)).not.toThrow();
    expect(new URL(site).origin).toBe(new URL(TEST_SITE).origin);
  });

  it('deux rendus successifs voient le même site (voie résolue une seule fois)', async () => {
    const a = (await renderWithSite(SiteProbe)).match(/data-site="([^"]*)"/)?.[1];
    const b = (await renderWithSite(SiteProbe)).match(/data-site="([^"]*)"/)?.[1];
    expect(a).toBe(b);
  });
});

describe('_container — détection de la voie', () => {
  it('aboutit à l’une des deux voies connues, sans lever', async () => {
    await expect(voieUtilisee()).resolves.toMatch(/^(publique|patch-interne)$/);
  });

  it('la voie est mémorisée : deux appels rendent la même valeur', async () => {
    expect(await voieUtilisee()).toBe(await voieUtilisee());
  });
});
