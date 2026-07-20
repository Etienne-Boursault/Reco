/**
 * Tests StatChart — F-H-10/11/12, F-M-5.
 *
 *  - F-H-10 : `<title>` enfant DIRECT du `<svg>` (a11y graphique).
 *  - F-H-11 : labels — > 12 barres ⇒ 1 label / N ; sinon tronquer à 8 chars + …
 *  - F-H-12 : pas d'attribut `height` sur le `<svg>` ; aspect-ratio CSS.
 *  - F-M-5  : prop `emptyKey` permet de surcharger `emptyMessage` via i18n.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import StatChart from '../../src/components/StatChart.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(StatChart as any, { props });
}

describe('StatChart — A11y / labels / dimensions', () => {
  it('F-H-10 : <title> enfant direct du <svg> avec le titre', async () => {
    const html = await render({
      title: 'Répartition par type',
      bars: [{ label: 'film', value: 10 }],
    });
    // <svg ...><title>Répartition par type</title>... — premier enfant.
    expect(html).toMatch(/<svg[^>]*>\s*<title>Répartition par type<\/title>/);
  });

  it('F-H-12 : pas d\'attribut height sur le <svg>', async () => {
    const html = await render({
      title: 'x',
      bars: [{ label: 'a', value: 1 }],
    });
    const svgTag = html.match(/<svg[^>]*>/)?.[0] ?? '';
    expect(svgTag).not.toMatch(/\sheight=/);
  });

  it('F-H-12 : aspect-ratio CSS posé sur le <svg>', async () => {
    const html = await render({
      title: 'x',
      bars: [{ label: 'a', value: 1 }],
    });
    const svgTag = html.match(/<svg[^>]*>/)?.[0] ?? '';
    expect(svgTag).toMatch(/aspect-ratio:\s*\d+\s*\/\s*\d+/);
  });

  it('F-H-11 : ≤ 12 barres ⇒ libellés tronqués à 8 chars + ellipsis', async () => {
    const bars = Array.from({ length: 5 }, (_, i) => ({
      label: `LibelléTrèsLong${i}`,
      value: i + 1,
    }));
    const html = await render({ title: 'x', bars });
    // Premier libellé devrait être tronqué (8 chars + …)
    expect(html).toMatch(/>LibelléT…</);
  });

  it('F-H-11 : > 12 barres ⇒ affiche 1 label sur N (Math.ceil(n/12))', async () => {
    const bars = Array.from({ length: 24 }, (_, i) => ({
      label: `m${i.toString().padStart(2, '0')}`,
      value: i,
    }));
    const html = await render({ title: 'monthly', bars });
    // ceil(24/12) = 2 → bars 0, 2, 4… affichées ; 1, 3, 5… vides.
    // On compte les <text class="bar-label">…</text> non vides.
    const labels = [...html.matchAll(/<text[^>]*class="bar-label"[^>]*>([^<]*)<\/text>/g)];
    const nonEmpty = labels.filter((m) => m[1].trim().length > 0);
    expect(labels.length).toBe(24);
    expect(nonEmpty.length).toBe(12);
  });

  it('F-M-5 : emptyKey override le message via i18n', async () => {
    const html = await render({
      title: 'Répartition',
      bars: [],
      emptyKey: 'stats.empty.typeDistribution',
    });
    expect(html).toContain('Pas encore assez de données.');
  });

  it('fallback emptyMessage si emptyKey absent', async () => {
    const html = await render({
      title: 'x',
      bars: [],
      emptyMessage: 'custom vide',
    });
    expect(html).toContain('custom vide');
  });
});
