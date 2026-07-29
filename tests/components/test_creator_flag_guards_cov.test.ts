/**
 * `CreatorFlag.astro` — gardes de robustesse sur une fiche incomplète.
 *
 * Le fichier curé impose aujourd'hui `source` et fixe toujours `severity`
 * (cf. le filtre de `src/data/creatorFlags.ts`). Le composant se protège
 * quand même des deux absences :
 *  - `severity` manquante → on retombe sur `accusation`, la formulation
 *    prudente (présomption d'innocence) ;
 *  - `source` manquante → aucun lien « Source ↗ » n'est rendu, plutôt qu'un
 *    `href` vide.
 *
 * Ces deux branches ne sont atteignables qu'en mockant la couche de données —
 * c'est la frontière du composant.
 */
import { describe, it, expect, vi } from 'vitest';

const flag: { situation: string; source?: string; severity?: string } = {
  situation: 'Situation décrite sans métadonnée complète.',
};
vi.mock('../../src/data/creatorFlags', () => ({
  creatorFlag: (name: string | null | undefined) => (name === 'Fiche Partielle' ? flag : null),
}));

const { experimental_AstroContainer: AstroContainer } = await import('astro/container');
const CreatorFlag = (await import('../../src/components/CreatorFlag.astro')).default;

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(CreatorFlag as any, { props });
}

describe('CreatorFlag — fiche sans severity', () => {
  it('retombe sur « accusation » (formulation prudente)', async () => {
    const html = await render({ name: 'Fiche Partielle' });
    expect(html).toContain('data-severity="accusation"');
    expect(html).toContain('Créateur mis en cause — voir la situation');
  });

  it('même repli sur la pastille non-interactive', async () => {
    const html = await render({ name: 'Fiche Partielle', interactive: false });
    expect(html).toContain('data-severity="accusation"');
  });
});

describe('CreatorFlag — fiche sans source', () => {
  it('n’émet aucun lien « Source ↗ »', async () => {
    const html = await render({ name: 'Fiche Partielle' });
    expect(html).toContain('Situation décrite sans métadonnée complète.');
    expect(html).not.toContain('creator-flag-src');
    expect(html).not.toContain('Source ↗');
  });

  it('avec une source, le lien réapparaît', async () => {
    flag.source = 'https://exemple.test/article';
    try {
      const html = await render({ name: 'Fiche Partielle' });
      expect(html).toContain('creator-flag-src');
      expect(html).toContain('href="https://exemple.test/article"');
    } finally {
      delete flag.source;
    }
  });
});
