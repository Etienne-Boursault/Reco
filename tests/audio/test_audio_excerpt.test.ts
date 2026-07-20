/**
 * Tests de rendu `AudioExcerpt.astro` via l'Astro Container API.
 * On vérifie les trois conditions (YouTube, Acast, vide) + la lazy iframe.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import AudioExcerpt from '../../src/components/AudioExcerpt.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(AudioExcerpt as any, { props });
}

describe('AudioExcerpt — rendu conditionnel', () => {
  it('avec youtubeId + startSeconds → bouton reveal + iframe lazy', async () => {
    const html = await render({ youtubeId: 'abc123XYZ_-', startSeconds: 133 });
    expect(html).toContain('audio-trigger');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain('Écouter à 2m13s');
    // L'iframe est présente mais initialisée avec data-src (lazy reveal).
    expect(html).toContain('data-src="https://www.youtube-nocookie.com/embed/');
    expect(html).toContain('loading="lazy"');
    // Région révélée masquée par défaut.
    expect(html).toMatch(/<div[^>]*class="audio-frame"[^>]*hidden/);
  });

  it('avec acastUrl seul → lien externe Acast', async () => {
    const html = await render({
      acastUrl: 'https://shows.acast.com/un-bon-moment/episodes/foo',
    });
    expect(html).toContain('href="https://shows.acast.com/');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).not.toContain('youtube-nocookie.com');
  });

  it('sans aucune source → rendu vide', async () => {
    const html = await render({});
    // Pas de bouton ni d'iframe.
    expect(html).not.toContain('audio-trigger');
    expect(html).not.toContain('iframe');
  });

  it('youtubeId sans startSeconds → bouton "Écouter cet extrait"', async () => {
    const html = await render({ youtubeId: 'abc123XYZ_-' });
    expect(html).toContain('audio-trigger');
    expect(html).toContain('Écouter');
  });
});
