/**
 * Branches restantes de `AudioExcerpt.astro`.
 *
 * Le libellé du bouton et son nom accessible ont chacun deux formes selon
 * que le timecode est exploitable ou non, et selon qu'un titre d'épisode est
 * fourni. Un timecode négatif (donnée aberrante) doit dégrader proprement
 * vers « Écouter cet extrait » plutôt que produire « Écouter à -5s ».
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import AudioExcerpt from '../../src/components/AudioExcerpt.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(AudioExcerpt as any, { props });
}

const YT = 'abc123XYZ_-';

/** Nom accessible du bouton de déclenchement. */
function triggerAria(html: string): string {
  return html.match(/class="audio-trigger"[\s\S]*?aria-label="([^"]*)"/)?.[1] ?? '';
}

describe('AudioExcerpt — libellé du bouton', () => {
  it('timecode positif → « Écouter à 2m13s »', async () => {
    const html = await render({ youtubeId: YT, startSeconds: 133 });
    expect(html).toContain('Écouter à 2m13s');
  });

  it('timecode 0 → « Écouter à 0s » (début d’épisode assumé)', async () => {
    const html = await render({ youtubeId: YT, startSeconds: 0 });
    expect(html).toContain('Écouter à 0s');
  });

  it('timecode négatif (donnée aberrante) → repli « Écouter cet extrait »', async () => {
    const html = await render({ youtubeId: YT, startSeconds: -5 });
    expect(html).toContain('Écouter cet extrait');
    expect(html).not.toContain('Écouter à');
  });

  it('startSeconds null → traité comme 0', async () => {
    const html = await render({ youtubeId: YT, startSeconds: null });
    expect(html).toContain('Écouter à 0s');
  });
});

describe('AudioExcerpt — nom accessible du bouton', () => {
  it('timecode verbalisé en clair, sans titre', async () => {
    const aria = triggerAria(await render({ youtubeId: YT, startSeconds: 133 }));
    expect(aria).toBe('Écouter cet extrait à 2 minutes 13 secondes');
  });

  it('timecode + titre d’épisode', async () => {
    const aria = triggerAria(
      await render({ youtubeId: YT, startSeconds: 133, title: 'Épisode 12' }),
    );
    expect(aria).toBe('Écouter cet extrait à 2 minutes 13 secondes — Épisode 12');
  });

  it('timecode inexploitable, sans titre → libellé nu', async () => {
    const aria = triggerAria(await render({ youtubeId: YT, startSeconds: -5 }));
    expect(aria).toBe('Écouter cet extrait');
  });

  it('timecode inexploitable, avec titre → libellé + titre', async () => {
    const aria = triggerAria(
      await render({ youtubeId: YT, startSeconds: -5, title: 'Épisode 12' }),
    );
    expect(aria).toBe('Écouter cet extrait — Épisode 12');
  });
});

describe('AudioExcerpt — région révélée et iframe', () => {
  it('sans titre, la région et l’iframe reprennent le libellé i18n générique', async () => {
    const html = await render({ youtubeId: YT, startSeconds: 10 });
    expect(html).toContain('aria-label="Extrait YouTube de l’épisode"');
    expect(html).toMatch(/<iframe[^>]*title="Extrait YouTube de l’épisode"/);
  });

  it('avec titre, la région et l’iframe portent ce titre', async () => {
    const html = await render({ youtubeId: YT, startSeconds: 10, title: 'Épisode 12' });
    expect(html).toMatch(/class="audio-frame"[\s\S]*?aria-label="Épisode 12"/);
    expect(html).toMatch(/<iframe[^>]*title="Épisode 12"/);
  });

  it('l’id de région combine l’identifiant fourni et le timecode', async () => {
    const html = await render({ youtubeId: YT, startSeconds: 133, id: 'men-1' });
    expect(html).toContain('id="audio-excerpt-men-1-133"');
    expect(html).toContain('aria-controls="audio-excerpt-men-1-133"');
  });

  it('sans id fourni, un identifiant aléatoire évite les collisions', async () => {
    const a = (await render({ youtubeId: YT, startSeconds: 1 })).match(/id="(audio-excerpt-[^"]+)"/)?.[1];
    const b = (await render({ youtubeId: YT, startSeconds: 1 })).match(/id="(audio-excerpt-[^"]+)"/)?.[1];
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });

  it('endSeconds est propagé à l’URL d’embed', async () => {
    const html = await render({ youtubeId: YT, startSeconds: 10, endSeconds: 40 });
    expect(html).toContain('end=40');
  });
});

describe('AudioExcerpt — repli Acast', () => {
  it('youtubeId vide + acastUrl → lien externe uniquement', async () => {
    const html = await render({
      youtubeId: null,
      acastUrl: 'https://shows.acast.com/ubm/episodes/x',
    });
    expect(html).toContain('audio-external');
    expect(html).toContain('Écouter sur Acast');
    expect(html).not.toContain('<iframe');
  });

  it('ni YouTube ni Acast → aucun élément de lecture rendu', async () => {
    const html = await render({ youtubeId: null, acastUrl: null });
    expect(html).not.toContain('audio-trigger');
    expect(html).not.toContain('<iframe');
    expect(html).not.toContain('audio-external');
  });
});
