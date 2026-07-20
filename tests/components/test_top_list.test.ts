/**
 * Tests TopList — F-M-16 (aria-rowcount + media print override).
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import TopList from '../../src/components/TopList.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(TopList as any, { props });
}

describe('TopList — A11y', () => {
  it('aria-rowcount posé si total > items.length', async () => {
    const html = await render({
      caption: 'Top',
      rows: [
        { label: 'a', count: 10 },
        { label: 'b', count: 5 },
      ],
      countHeader: 'mentions',
      emptyMessage: 'vide',
      total: 50,
    });
    expect(html).toMatch(/aria-rowcount="50"/);
  });

  it('aria-rowcount absent si total === items.length', async () => {
    const html = await render({
      caption: 'Top',
      rows: [{ label: 'a', count: 10 }],
      countHeader: 'mentions',
      emptyMessage: 'vide',
      total: 1,
    });
    expect(html).not.toMatch(/aria-rowcount=/);
  });

  it('aria-rowcount absent si total non fourni', async () => {
    const html = await render({
      caption: 'Top',
      rows: [{ label: 'a', count: 10 }],
      countHeader: 'mentions',
      emptyMessage: 'vide',
    });
    expect(html).not.toMatch(/aria-rowcount=/);
  });

  it('rend message vide quand rows est vide', async () => {
    const html = await render({
      caption: 'Top',
      rows: [],
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).toContain('Aucune donnée.');
  });
});
