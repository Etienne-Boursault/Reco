/**
 * Tests `GalleryCard.astro`, `GalleryGrid.astro` et `EmptyState.astro`.
 *
 * GalleryCard a deux rendus mutuellement exclusifs (X2) : `<a>` cliquable
 * quand `href` est fourni, `<article>` inerte sinon. Les deux doivent
 * produire le même contenu (type, titre, créateur·rice, compteur) — c'est
 * la duplication la plus fragile du composant, on la verrouille.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import GalleryCard from '../../src/components/GalleryCard.astro';
import GalleryGrid from '../../src/components/GalleryGrid.astro';
import EmptyState from '../../src/components/EmptyState.astro';

async function render(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Component: any,
  props: Record<string, unknown>,
  slots: Record<string, unknown> = {},
): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(Component, { props, slots });
}

const BASE = {
  id: 'itm-1',
  title: 'Parasite',
  types: ['film'],
  mentionCount: 3,
};

// ---------------------------------------------------------------------------
// GalleryCard
// ---------------------------------------------------------------------------
describe('GalleryCard — variante non cliquable (<article>)', () => {
  it('rend un <article> quand href est absent', async () => {
    const html = await render(GalleryCard, BASE);
    expect(html).toMatch(/<article class="gcard"/);
    expect(html).not.toContain('gcard--link');
  });

  it('expose l’id et les types en data-attributes', async () => {
    const html = await render(GalleryCard, { ...BASE, types: ['film', 'livre'] });
    expect(html).toContain('data-item-id="itm-1"');
    expect(html).toContain('data-types="film,livre"');
  });

  it('href null explicite est traité comme absent', async () => {
    const html = await render(GalleryCard, { ...BASE, href: null });
    expect(html).toMatch(/<article class="gcard"/);
  });
});

describe('GalleryCard — variante cliquable (<a>, X2)', () => {
  it('rend un <a> vers la page œuvre avec un nom accessible explicite', async () => {
    const html = await render(GalleryCard, { ...BASE, href: '/ubm/oeuvre/itm-1' });
    expect(html).toContain('gcard--link');
    expect(html).toContain('href="/ubm/oeuvre/itm-1"');
    expect(html).toContain('aria-label="Parasite — Voir la page complète de l’œuvre"');
  });
});

describe('GalleryCard — type primaire', () => {
  it('prend le premier type et son emoji', async () => {
    const html = await render(GalleryCard, { ...BASE, types: ['livre', 'film'] });
    expect(html).toContain('📖');
    expect(html).toContain('>Livre</p>');
  });

  it('liste de types vide → repli sur « autre »', async () => {
    const html = await render(GalleryCard, { ...BASE, types: [] });
    expect(html).toContain('✨');
    expect(html).toContain('>Autre</p>');
  });

  it('type inconnu → emoji et libellé de repli « autre »', async () => {
    const html = await render(GalleryCard, { ...BASE, types: ['zarbi'] });
    expect(html).toContain('✨');
    expect(html).toContain('>Autre</p>');
  });

  it('l’emoji est décoratif, le type reste annoncé par aria-label', async () => {
    const html = await render(GalleryCard, BASE);
    expect(html).toMatch(/<div class="gcard-icon" aria-hidden="true"[^>]*>🎬<\/div>/);
    expect(html).toContain('aria-label="Type : Film"');
  });
});

describe('GalleryCard — créateur·rice', () => {
  it('affiche le créateur quand il existe', async () => {
    const html = await render(GalleryCard, { ...BASE, creator: 'Bong Joon-ho' });
    expect(html).toContain('Bong Joon-ho');
  });

  it('sans créateur → aucune ligne créateur', async () => {
    const html = await render(GalleryCard, BASE);
    expect(html).not.toContain('gcard-creator');
  });

  it('créateur null → aucune ligne créateur', async () => {
    const html = await render(GalleryCard, { ...BASE, creator: null });
    expect(html).not.toContain('gcard-creator');
  });

  it('un créateur signalé porte la pastille ⚠️ non-interactive (valide dans un <a>)', async () => {
    const html = await render(GalleryCard, {
      ...BASE,
      creator: 'Roman Polanski',
      href: '/ubm/oeuvre/itm-1',
    });
    expect(html).toContain('creator-flag-dot');
    // Un <details> serait illégal à l'intérieur d'un <a>.
    expect(html).not.toContain('<details');
  });
});

describe('GalleryCard — compteur de mentions', () => {
  it('pluriel à partir de 2 mentions', async () => {
    const html = await render(GalleryCard, { ...BASE, mentionCount: 3 });
    expect(html).toContain('>mentions<');
  });

  it('singulier à 1 mention', async () => {
    const html = await render(GalleryCard, { ...BASE, mentionCount: 1 });
    expect(html).toContain('>mention<');
  });

  it('singulier à 0 mention', async () => {
    const html = await render(GalleryCard, { ...BASE, mentionCount: 0 });
    expect(html).toContain('>mention<');
  });
});

// ---------------------------------------------------------------------------
// GalleryGrid
// ---------------------------------------------------------------------------
const ENTRY = {
  id: 'itm-1',
  title: 'Parasite',
  types: ['film'],
  creator: 'Bong Joon-ho',
  mentionCount: 2,
};

describe('GalleryGrid — grille et compteur', () => {
  it('rend une liste de cartes avec le compteur et son libellé', async () => {
    const html = await render(GalleryGrid, {
      heading: 'Films',
      entries: [ENTRY],
      countLabel: 'films recommandés',
    });
    expect(html).toContain('films recommandés');
    expect(html).toMatch(/<span class="gal-count-n"[^>]*>1<\/span>/);
    expect(html).toContain('<ul class="gal-grid"');
    expect(html).toContain('Parasite');
  });

  it('la section porte le heading comme nom accessible', async () => {
    const html = await render(GalleryGrid, {
      heading: 'Films',
      entries: [ENTRY],
      countLabel: 'films',
    });
    expect(html).toMatch(/<section class="gal-section" aria-label="Films"/);
  });

  it('sans sourceId, les cartes ne sont pas cliquables', async () => {
    const html = await render(GalleryGrid, {
      heading: 'Films',
      entries: [ENTRY],
      countLabel: 'films',
    });
    expect(html).not.toContain('gcard--link');
  });

  it('avec sourceId, chaque carte pointe vers /<source>/oeuvre/<id> (X2)', async () => {
    const html = await render(GalleryGrid, {
      heading: 'Films',
      entries: [ENTRY],
      countLabel: 'films',
      sourceId: 'ubm',
    });
    expect(html).toContain('href="/ubm/oeuvre/itm-1"');
  });
});

describe('GalleryGrid — état vide', () => {
  it('aucune entrée → EmptyState avec le message par défaut', async () => {
    const html = await render(GalleryGrid, {
      heading: 'Films',
      entries: [],
      countLabel: 'films',
    });
    expect(html).toContain('Aucune recommandation pour cette galerie.');
    expect(html).not.toContain('gal-grid');
  });

  it('message et indice personnalisés sont transmis à EmptyState', async () => {
    const html = await render(GalleryGrid, {
      heading: 'Films',
      entries: [],
      countLabel: 'films',
      emptyMessage: 'Rien ici',
      emptyHint: 'Reviens plus tard',
    });
    expect(html).toContain('Rien ici');
    expect(html).toContain('Reviens plus tard');
  });
});

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------
describe('EmptyState', () => {
  it('rend le message dans une région role="status" (annoncée par les AT)', async () => {
    const html = await render(EmptyState, { message: 'Aucune recommandation' });
    expect(html).toMatch(/<p class="empty" role="status"/);
    expect(html).toContain('Aucune recommandation');
  });

  it('sans hint, aucun span .empty-hint', async () => {
    const html = await render(EmptyState, { message: 'Aucune recommandation' });
    expect(html).not.toContain('empty-hint');
  });

  it('avec hint, le texte d’aide est rendu sous le message', async () => {
    const html = await render(EmptyState, { message: 'Vide', hint: 'Lance le pipeline' });
    expect(html.indexOf('Vide')).toBeLessThan(html.indexOf('Lance le pipeline'));
    expect(html).toContain('empty-hint');
  });

  it('le slot permet d’ajouter une action', async () => {
    const html = await render(
      EmptyState,
      { message: 'Vide' },
      { default: '<a href="/">Retour</a>' },
    );
    expect(html).toContain('<a href="/">Retour</a>');
  });
});
