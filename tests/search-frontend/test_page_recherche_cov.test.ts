/**
 * tests/search-frontend/test_page_recherche_cov.test.ts
 *
 * Rendu unitaire de `src/pages/recherche.astro` via l'Astro Container API.
 *
 * Complète `test_recherche_page.test.ts`, qui inspecte `dist/` après build et
 * se skippe donc sans build préalable. La page est intégralement pilotée côté
 * client : ce qui compte ici, c'est le **contrat DOM** que le script attend
 * (`data-recherche-*`), plus le `noindex` (page utilitaire, ADR 0035) et
 * l'absence de duplication de la palette globale (P0-1).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import Recherche from '../../src/pages/recherche.astro';

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockImplementation(async () => []);
});

describe('/recherche', () => {
  const render = () => renderPage(Recherche, { path: '/recherche' });

  it('expose les points d’ancrage attendus par le script client', async () => {
    const html = await render();

    for (const hook of [
      'data-recherche-form',
      'data-recherche-input',
      'data-recherche-status',
      'data-recherche-results',
    ]) {
      expect(html).toContain(hook);
    }
  });

  it('le champ de recherche est étiqueté et de type `search`', async () => {
    const html = await render();

    expect(html).toContain('id="recherche-input"');
    expect(html).toContain('for="recherche-input"');
    expect(html).toContain('type="search"');
    expect(html).toContain('name="q"');
    expect(html).toContain('role="search"');
  });

  it('la zone de résultats est une région live annoncée', async () => {
    const html = await render();

    expect(html).toContain('aria-live="polite"');
    expect(html).toMatch(/<output[^>]*class="search-results"/);
  });

  it('est en noindex (page utilitaire, ADR 0035)', async () => {
    expect(await render()).toContain('<meta name="robots" content="noindex, nofollow">');
  });

  it('ne monte pas de seconde palette (P0-1 : elle vient du Layout)', async () => {
    const html = await render();
    const palettes = html.match(/id="search-palette"/g) ?? [];

    expect(palettes.length).toBeLessThanOrEqual(1);
  });

  it('affiche le titre et l’indication de recherche', async () => {
    const text = visibleText(await render());

    expect(text).toContain('Recherche');
    expect(text).toContain('Rechercher une œuvre, un épisode, un invité…');
    expect(text).toContain('Tape au moins deux caractères');
  });
});
