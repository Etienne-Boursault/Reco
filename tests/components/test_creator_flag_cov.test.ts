/**
 * Tests `CreatorFlag.astro` — info-bulle « situation du créateur ».
 *
 * Règle produit : le composant n'invente RIEN. Il n'affiche que ce qui est
 * déclaré et sourcé dans `src/data/creator-flags.json`, et reste totalement
 * muet pour un créateur absent du fichier.
 *
 * Deux rendus mutuellement exclusifs :
 *  - `interactive` (défaut) : `<details>` avec la source cliquable ;
 *  - `interactive={false}` : simple `<span title>` — un `<details>`/`<a>`
 *    serait illégal à l'intérieur d'une carte-lien (WorkCard, GalleryCard).
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import CreatorFlag from '../../src/components/CreatorFlag.astro';

async function render(props: Record<string, unknown> = {}): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(CreatorFlag as any, { props });
}

describe('CreatorFlag — silence par défaut', () => {
  it('sans prop name → rendu vide', async () => {
    expect((await render()).trim()).toBe('');
  });

  it('name null → rendu vide', async () => {
    expect((await render({ name: null })).trim()).toBe('');
  });

  it('name vide → rendu vide', async () => {
    expect((await render({ name: '' })).trim()).toBe('');
  });

  it('créateur absent du fichier curé → rendu vide', async () => {
    expect((await render({ name: 'Alexandre Astier' })).trim()).toBe('');
  });

  it('reste vide même en mode non-interactif', async () => {
    expect((await render({ name: 'Alexandre Astier', interactive: false })).trim()).toBe('');
  });
});

describe('CreatorFlag — rendu interactif (<details>)', () => {
  it('accusation : summary « mis en cause » + texte factuel + source', async () => {
    const html = await render({ name: 'Woody Allen' });
    expect(html).toMatch(/<details class="creator-flag" data-severity="accusation"/);
    expect(html).toContain('Créateur mis en cause — voir la situation');
    expect(html).toContain('Dylan Farrow');
    expect(html).toContain('href="https://www.bbc.com/news/entertainment-arts-56563149"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toMatch(/<div class="creator-flag-panel" role="note"/);
  });

  it('condamnation : libellé et data-severity distincts', async () => {
    const html = await render({ name: 'Roman Polanski' });
    expect(html).toContain('data-severity="condamnation"');
    expect(html).toContain('Créateur condamné — voir la situation');
  });

  it('interactive=true explicite donne le même rendu que le défaut', async () => {
    const parDefaut = await render({ name: 'Roman Polanski' });
    const explicite = await render({ name: 'Roman Polanski', interactive: true });
    expect(explicite).toBe(parDefaut);
  });

  it('le ⚠️ du summary est décoratif, le nom accessible vient de aria-label', async () => {
    const html = await render({ name: 'Woody Allen' });
    expect(html).toMatch(/<span aria-hidden="true"[^>]*>⚠️<\/span>/);
    expect(html).toMatch(/<summary aria-label="[^"]+" title="[^"]+"/);
  });

  it('la correspondance de nom ignore casse et accents', async () => {
    const exact = await render({ name: 'Seb Mellia' });
    const accentue = await render({ name: 'SEB MÉLLIA' });
    expect(exact).toContain('creator-flag');
    expect(accentue).toContain('creator-flag');
  });

  it('un alias déclaré du créateur déclenche le même signalement', async () => {
    const html = await render({ name: 'InThePanda' });
    expect(html).toContain('Numerama');
  });
});

describe('CreatorFlag — rendu non-interactif (pastille)', () => {
  it('rend un <span role="img"> sans <details> ni <a>', async () => {
    const html = await render({ name: 'Roman Polanski', interactive: false });
    expect(html).toMatch(/<span class="creator-flag-dot" data-severity="condamnation" role="img"/);
    expect(html).not.toContain('<details');
    expect(html).not.toContain('<a ');
  });

  it('le nom accessible concatène le libellé de gravité et la situation', async () => {
    const html = await render({ name: 'Roman Polanski', interactive: false });
    expect(html).toMatch(/aria-label="Créateur condamné — voir la situation : A plaidé coupable/);
  });

  it('la situation est aussi en title (info-bulle souris)', async () => {
    const html = await render({ name: 'Woody Allen', interactive: false });
    expect(html).toMatch(/title="Créateur mis en cause — voir la situation : /);
  });
});
