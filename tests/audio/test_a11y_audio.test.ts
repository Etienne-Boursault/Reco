/**
 * Tests d'accessibilité du composant AudioExcerpt.
 * Vérifie aria-label lisible (h/m/s en clair), aria-expanded/pressed,
 * title sur l'iframe, pas d'autoplay.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import AudioExcerpt from '../../src/components/AudioExcerpt.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(AudioExcerpt as any, { props });
}

describe('AudioExcerpt — accessibilité WCAG AA', () => {
  it('aria-label déroule le timecode lisible (2 minutes 13 secondes)', async () => {
    const html = await render({ youtubeId: 'abc', startSeconds: 133 });
    expect(html).toContain('2 minutes 13 secondes');
  });

  it('aria-expanded et aria-pressed initialisés à false', async () => {
    const html = await render({ youtubeId: 'abc', startSeconds: 10 });
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-pressed="false"');
  });

  it('iframe a un title descriptif', async () => {
    const html = await render({
      youtubeId: 'abc',
      startSeconds: 10,
      title: 'Extrait : Apocalypse Now',
    });
    expect(html).toMatch(/<iframe[^>]*title="Extrait : Apocalypse Now"/);
  });

  it('iframe lazy + pas d\'autoplay côté URL', async () => {
    const html = await render({ youtubeId: 'abc', startSeconds: 10 });
    expect(html).toContain('loading="lazy"');
    expect(html).toContain('autoplay=0');
  });

  it('lien acast porte le suffixe externalLinkSuffix', async () => {
    const html = await render({ acastUrl: 'https://shows.acast.com/x/y' });
    expect(html).toContain('(nouvel onglet)');
  });

  it('aria-controls pointe vers la région révélée', async () => {
    const html = await render({ youtubeId: 'abc', startSeconds: 10, id: 'ex1' });
    const m = html.match(/aria-controls="([^"]+)"/);
    expect(m).not.toBeNull();
    const regionId = m![1];
    expect(html).toContain(`id="${regionId}"`);
  });
});
