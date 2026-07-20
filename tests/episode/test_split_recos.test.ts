/**
 * Tests du helper pur `splitEpisodeRecos` (src/lib/episode/splitRecos).
 *
 * Décision produit : les œuvres d'invité·es (guestWork) restent comptées comme
 * des recos partout ; SEULE la page épisode les présente à part. Ce helper
 * isole cette répartition en trois seaux mutuellement exclusifs.
 */
import { describe, it, expect } from 'vitest';
import {
  splitEpisodeRecos,
  type EpisodeRecoLike,
} from '../../src/lib/episode/splitRecos';

function reco(id: string, over: Partial<EpisodeRecoLike> = {}): EpisodeRecoLike & { id: string } {
  return { id, ...over };
}

describe('splitEpisodeRecos', () => {
  it('classe une reco spontanée (kind absent) dans spontaneous', () => {
    const { spontaneous, guestWorks, citations } = splitEpisodeRecos([reco('a')]);
    expect(spontaneous.map((r) => (r as { id: string }).id)).toEqual(['a']);
    expect(guestWorks).toHaveLength(0);
    expect(citations).toHaveLength(0);
  });

  it('exclut les guestWork des spontanées et les met dans guestWorks', () => {
    const { spontaneous, guestWorks } = splitEpisodeRecos([
      reco('a'),
      reco('b', { guestWork: true }),
    ]);
    expect(spontaneous.map((r) => (r as { id: string }).id)).toEqual(['a']);
    expect(guestWorks.map((r) => (r as { id: string }).id)).toEqual(['b']);
  });

  it('classe les citations à part, intactes', () => {
    const { spontaneous, guestWorks, citations } = splitEpisodeRecos([
      reco('a'),
      reco('c', { kind: 'citation' }),
    ]);
    expect(spontaneous.map((r) => (r as { id: string }).id)).toEqual(['a']);
    expect(guestWorks).toHaveLength(0);
    expect(citations.map((r) => (r as { id: string }).id)).toEqual(['c']);
  });

  it('une citation prime sur guestWork (cas legacy) → reste en citations', () => {
    const { spontaneous, guestWorks, citations } = splitEpisodeRecos([
      reco('x', { kind: 'citation', guestWork: true }),
    ]);
    expect(spontaneous).toHaveLength(0);
    expect(guestWorks).toHaveLength(0);
    expect(citations.map((r) => (r as { id: string }).id)).toEqual(['x']);
  });

  it('préserve l\'ordre d\'entrée dans chaque seau', () => {
    const { spontaneous, guestWorks, citations } = splitEpisodeRecos([
      reco('s1'),
      reco('g1', { guestWork: true }),
      reco('c1', { kind: 'citation' }),
      reco('s2'),
      reco('g2', { guestWork: true }),
    ]);
    expect(spontaneous.map((r) => (r as { id: string }).id)).toEqual(['s1', 's2']);
    expect(guestWorks.map((r) => (r as { id: string }).id)).toEqual(['g1', 'g2']);
    expect(citations.map((r) => (r as { id: string }).id)).toEqual(['c1']);
  });

  it('liste vide → trois seaux vides', () => {
    const { spontaneous, guestWorks, citations } = splitEpisodeRecos([]);
    expect(spontaneous).toHaveLength(0);
    expect(guestWorks).toHaveLength(0);
    expect(citations).toHaveLength(0);
  });
});
