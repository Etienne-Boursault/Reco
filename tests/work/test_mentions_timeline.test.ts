/**
 * Tests MentionsTimeline — badge « œuvre d'invité » (CR Story 4, MEDIUM-3).
 *
 * Cohérence avec RecoCard : une mention marquée `guestWork` affiche le badge
 * 🎤 dans la timeline de la page œuvre. Sans le flag → aucun badge.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import MentionsTimeline from '../../src/components/MentionsTimeline.astro';
import type { JoinedMention } from '../../src/lib/work/aggregator';

function joined(over: Partial<JoinedMention['mention']> = {}): JoinedMention {
  return {
    mention: {
      id: 'm1',
      itemId: 'i1',
      sourceRef: { sourceId: 'ubm', episodeGuid: 'ep-1' },
      kind: 'reco',
      status: 'validated',
      ...over,
    },
    episode: {
      guid: 'ep-1',
      title: 'Épisode test',
      date: new Date('2026-03-01'),
      youtubeUrl: 'https://www.youtube.com/watch?v=ABCDEFGHIJK',
    },
  };
}

async function render(mentions: JoinedMention[]): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(MentionsTimeline as any, {
    props: { sourceId: 'ubm', mentions },
  });
}

describe('MentionsTimeline — badge œuvre d\'invité', () => {
  it('affiche le badge ⭐ quand la mention est guestWork', async () => {
    const html = await render([joined({ guestWork: true })]);
    // M3 : ⭐ (cohérent avec RecoCard, évite la collision 🎤 / type artiste).
    expect(html).toContain('⭐');
    // Libellé 2026-07-07 : guestWork couvre invité·es ET hosts.
    expect(html).toContain('Leur œuvre');
  });

  it('n\'utilise plus 🎤 pour le badge guestWork (M3)', async () => {
    const html = await render([joined({ guestWork: true })]);
    expect(html).not.toContain('🎤');
  });

  it('n\'affiche aucun badge guestWork sans le flag', async () => {
    const html = await render([joined()]);
    expect(html).not.toContain('⭐');
  });
});
