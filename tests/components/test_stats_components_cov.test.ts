/**
 * Branches restantes de `StatCard.astro`, `TopList.astro` et
 * `StatChart.astro` (pages /stats).
 *
 * Ces trois composants sont déjà couverts en lignes ; il manquait les cas
 * NON nominaux : unité absente, ligne sans lien, ligne sans sous-libellé,
 * total tronqué, série vide et série entièrement à zéro.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import StatCard from '../../src/components/StatCard.astro';
import TopList from '../../src/components/TopList.astro';
import StatChart from '../../src/components/StatChart.astro';

async function render(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Component: any,
  props: Record<string, unknown>,
): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(Component, { props });
}

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------
describe('StatCard — unité optionnelle', () => {
  it('sans unit, aucun span .unit', async () => {
    const html = await render(StatCard, { value: 42, label: 'épisodes' });
    expect(html).not.toContain('class="unit"');
  });

  it('avec unit, le suffixe court est rendu à côté du chiffre', async () => {
    const html = await render(StatCard, { value: 42, label: 'épisodes', unit: 'podcasts' });
    expect(html).toMatch(/<span class="unit"[^>]*>podcasts<\/span>/);
    // L'unité reste dans le bloc aria-hidden : elle n'est pas re-verbalisée.
    expect(html).toMatch(/class="value" aria-hidden="true"/);
  });
});

// ---------------------------------------------------------------------------
// TopList
// ---------------------------------------------------------------------------
const ROWS = [
  { label: 'Adrien Ménielle', count: 12 },
  { label: 'Parasite', count: 7 },
];

describe('TopList — état vide', () => {
  it('aucune ligne → message d’état, pas de <table>', async () => {
    const html = await render(TopList, {
      caption: 'Top invités',
      rows: [],
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).toMatch(/<p class="empty" role="status"[^>]*>Aucune donnée\.<\/p>/);
    expect(html).not.toContain('<table');
  });
});

describe('TopList — contenu des lignes', () => {
  it('table sémantique avec caption et en-têtes de colonnes', async () => {
    const html = await render(TopList, {
      caption: 'Top invités',
      rows: ROWS,
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).toMatch(/<caption[^>]*>Top invités<\/caption>/);
    expect(html).toContain('scope="col"');
    expect(html).toContain('mentions');
    expect(html).toContain('>1</td>');
    expect(html).toContain('>2</td>');
  });

  it('ligne sans href → <span>, pas de lien', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: [{ label: 'Sans lien', count: 3 }],
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).toMatch(/<span[^>]*>Sans lien<\/span>/);
    expect(html).not.toContain('<a href');
  });

  it('ligne avec href → lien cliquable', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: [{ label: 'Avec lien', count: 3, href: '/ubm/invite/x' }],
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).toContain('href="/ubm/invite/x"');
    expect(html).toContain('Avec lien');
  });

  it('ligne sans sub → aucun span .sub', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: ROWS,
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).not.toContain('class="sub"');
  });

  it('ligne avec sub → sous-libellé séparé par une puce', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: [{ label: 'Parasite', count: 7, sub: 'Film' }],
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).toMatch(/<span class="sub"[^>]*> · Film<\/span>/);
  });
});

describe('TopList — aria-rowcount sur liste tronquée (F-M-16)', () => {
  it('total absent → pas d’aria-rowcount', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: ROWS,
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
    });
    expect(html).not.toContain('aria-rowcount');
  });

  it('total > nombre de lignes → aria-rowcount informe de la troncature', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: ROWS,
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
      total: 50,
    });
    expect(html).toContain('aria-rowcount="50"');
  });

  it('total égal au nombre de lignes → attribut omis (aucune info à donner)', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: ROWS,
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
      total: 2,
    });
    expect(html).not.toContain('aria-rowcount');
  });

  it('total inférieur au nombre de lignes → attribut omis', async () => {
    const html = await render(TopList, {
      caption: 'Top',
      rows: ROWS,
      countHeader: 'mentions',
      emptyMessage: 'Aucune donnée.',
      total: 1,
    });
    expect(html).not.toContain('aria-rowcount');
  });
});

// ---------------------------------------------------------------------------
// StatChart
// ---------------------------------------------------------------------------
describe('StatChart — série vide (M26-11)', () => {
  it('affiche le message vide dans le SVG et dans la table accessible', async () => {
    const html = await render(StatChart, { title: 'Par type', bars: [] });
    expect(html).toContain('class="empty-text"');
    expect(html).toContain('colspan="2"');
    expect(html).not.toContain('class="bar-group"');
  });

  it('pose aria-describedby vers un texte sr-only (F-L-5)', async () => {
    const html = await render(StatChart, { title: 'Par type', bars: [] });
    const id = html.match(/aria-describedby="([^"]+)"/)?.[1];
    expect(id).toBeTruthy();
    expect(html).toMatch(new RegExp(`<p id="${id}" class="sr-only"`));
  });

  it('ariaLabel explicite remplace le message vide dans le texte sr-only', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [],
      ariaLabel: 'Graphique sans donnée pour l’instant',
    });
    expect(html).toContain('Graphique sans donnée pour l’instant');
  });

  it('emptyKey i18n prime sur emptyMessage (F-M-5)', async () => {
    const parDefaut = await render(StatChart, { title: 'Par mois', bars: [] });
    const parCle = await render(StatChart, {
      title: 'Par mois',
      bars: [],
      emptyKey: 'stats.empty.monthly',
    });
    expect(parCle).not.toBe(parDefaut);
  });

  it('emptyMessage brut est utilisé quand aucune clé n’est fournie', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [],
      emptyMessage: 'Rien à montrer',
    });
    expect(html).toContain('Rien à montrer');
  });
});

describe('StatChart — série non vide', () => {
  it('une barre par entrée, avec <title> SVG détaillé', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [
        { label: 'Films', value: 30 },
        { label: 'Livres', value: 10 },
      ],
    });
    expect(html.match(/class="bar-group"/g)?.length).toBe(2);
    expect(html).toContain('Films — 30');
    // Série non vide : pas de description additionnelle (F-L-5).
    expect(html).not.toContain('aria-describedby');
    expect(html).not.toContain('class="sr-only"');
  });

  it('série entièrement à zéro → pourcentages à 0 % et barres de hauteur nulle', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [
        { label: 'Films', value: 0 },
        { label: 'Livres', value: 0 },
      ],
    });
    expect(html).toMatch(/<rect[^>]*height="0"/);
    expect(html).toContain('Films — 0 (0%)');
  });

  it('une valeur > 0 garde une hauteur minimale visible (M26-7)', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [
        { label: 'Gros', value: 10000 },
        { label: 'Petit', value: 1 },
      ],
    });
    const hauteurs = [...html.matchAll(/<rect[^>]*height="([\d.]+)"/g)].map((m) => Number(m[1]));
    expect(hauteurs).toHaveLength(2);
    expect(Math.min(...hauteurs)).toBeGreaterThanOrEqual(2);
  });

  // F-H-11 REVISE le 2026-08-19 : ces deux tests exigeaient une troncature a
  // huit caracteres et un libelle sur N. Le graphique en devenait illisible —
  // « affiche tous les noms de toutes les colonnes ». On INCLINE desormais
  // plutot que de couper ; l'intention anti-chevauchement est la meme.
  it('libellé long rendu en entier (F-H-11 révisé)', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [{ label: 'Documentaires animaliers', value: 4 }],
    });
    expect(html).toContain('Documentaires animaliers');
    expect(html).not.toContain('Document…');
  });

  it('série > 12 barres → tous les libellés rendus, aucun vide', async () => {
    const bars = Array.from({ length: 26 }, (_, i) => ({ label: `M${i}`, value: i + 1 }));
    const html = await render(StatChart, { title: 'Par mois', bars });
    const labels = [...html.matchAll(/class="bar-label"[^>]*>([^<]*)</g)].map((m) => m[1]);
    expect(labels).toHaveLength(26);
    expect(labels).toContain('M0');
    expect(labels.filter((l) => l === '')).toHaveLength(0);
  });

  it('en-têtes de colonnes personnalisables', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [{ label: 'Films', value: 3 }],
      valueHeader: 'occurrences',
      categoryHeader: 'catégorie',
    });
    expect(html).toContain('occurrences');
    expect(html).toContain('catégorie');
  });

  it('hauteur personnalisée pilote le ratio du SVG (F-H-12)', async () => {
    const html = await render(StatChart, {
      title: 'Par type',
      bars: [{ label: 'Films', value: 3 }],
      height: 400,
    });
    expect(html).toContain('aspect-ratio: 600 / 400');
    expect(html).toContain('viewBox="0 0 600 400"');
    expect(html).not.toMatch(/<svg[^>]*\sheight="/);
  });
});
