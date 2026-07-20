/**
 * Tests StatCard — F-H-9 (suppression double announcement SR).
 *
 * Le gros chiffre est `aria-hidden=true`. Une seule verbalisation passe au
 * lecteur d'écran via `.sr-only` (la quantité formatée). Le `<h3>` porte le
 * libellé court (« recommandations ») pour la navigation landmarks ; le
 * `aria-labelledby` du group reste lié à ce `<h3>` — pas de doublon avec
 * le `.sr-only`.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import StatCard from '../../src/components/StatCard.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(StatCard as any, { props });
}

describe('StatCard — A11y', () => {
  it('le gros chiffre est aria-hidden', async () => {
    const html = await render({ value: 2866, label: 'recommandations' });
    expect(html).toMatch(/<p[^>]*class="value"[^>]*aria-hidden="true"/);
  });

  it('expose une seule verbalisation SR (sr-only) — pas de doublon', async () => {
    const html = await render({ value: 2866, label: 'recommandations' });
    const srMatches = html.match(/class="sr-only"/g) ?? [];
    expect(srMatches.length).toBe(1);
    // F-H-9 : .sr-only porte UNIQUEMENT la quantité formatée (pas le label,
    // déjà annoncé via le <h3> cible du aria-labelledby).
    const srText = html.match(/class="sr-only"[^>]*>([^<]+)</)?.[1] ?? '';
    // Locale FR : séparateur de milliers = espace fine insécable (NBSP/NNBSP).
    expect(srText).toMatch(/2\D866/);
    expect(srText).not.toMatch(/recommandations/);
  });

  it('le <h3> porte le libellé court et l\'id de aria-labelledby', async () => {
    const html = await render({ value: 12, label: 'épisodes' });
    const idMatch = html.match(/aria-labelledby="([^"]+)"/);
    expect(idMatch).not.toBeNull();
    const id = idMatch![1];
    expect(html).toMatch(new RegExp(`<h3[^>]*id="${id}"[^>]*>épisodes</h3>`));
  });

  it('id déterministe (pas de Math.random) — stable entre deux rendus', async () => {
    const a = await render({ value: 1, label: 'foo' });
    const b = await render({ value: 1, label: 'foo' });
    const idA = a.match(/aria-labelledby="([^"]+)"/)?.[1];
    const idB = b.match(/aria-labelledby="([^"]+)"/)?.[1];
    expect(idA).toBe(idB);
  });

  it('respecte srLabel custom si fourni', async () => {
    const html = await render({
      value: 1000,
      label: 'œuvres',
      srLabel: '1 000 œuvres référencées',
    });
    expect(html).toContain('1 000 œuvres référencées');
  });

  it('idPrefix custom (F-N-6) évite les collisions inter-sections', async () => {
    const html = await render({ value: 5, label: 'films', idPrefix: 'top-cards' });
    expect(html).toMatch(/id="top-cards-/);
  });
});
