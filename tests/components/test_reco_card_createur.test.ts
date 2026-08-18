/**
 * Le créateur n'est affiché que s'il APPORTE quelque chose au titre.
 *
 * Quatre-vingt-cinq recos portent un créateur identique à leur titre — le cas
 * normal du type `artiste`, où le titre EST la personne. La carte répétait
 * alors le même nom deux fois, une fois en titre et une fois dessous
 * (relevé le 2026-08-18).
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeEach, describe, expect, it } from 'vitest';
import RecoCard from '../../src/components/RecoCard.astro';

let container: AstroContainer;
beforeEach(async () => {
  container = await AstroContainer.create();
});

const rendre = (reco: Record<string, unknown>) =>
  container.renderToString(RecoCard, {
    props: {
      reco: { id: 'ubm-1', title: 'T', types: ['artiste'], links: [], ...reco },
      sourceId: 'un-bon-moment',
    },
  });

describe('RecoCard — ligne créateur', () => {
  it('affiche le créateur quand il diffère du titre', async () => {
    const html = await rendre({ title: 'OK Computer', creator: 'Radiohead' });
    expect(html).toContain('creator-name');
    expect(html).toContain('Radiohead');
  });

  it('le TAIT quand il répète le titre — le défaut du 2026-08-18', async () => {
    const html = await rendre({ title: 'Radiohead', creator: 'Radiohead' });
    expect(html).not.toContain('creator-name');
  });

  it('ignore la casse et les espaces de bordure', async () => {
    const html = await rendre({ title: 'Barbara', creator: '  barbara ' });
    expect(html).not.toContain('creator-name');
  });

  it('ne rend rien quand le créateur est absent', async () => {
    const html = await rendre({ title: 'Un titre' });
    expect(html).not.toContain('creator-name');
  });
});
