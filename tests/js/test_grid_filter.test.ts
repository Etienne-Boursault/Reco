// @vitest-environment happy-dom
/**
 * Tests de `src/utils/gridFilter.ts` — la boucle « filtrer les enfants →
 * compter → annoncer » partagée par les deux grilles de `SourceCatalog.astro`.
 *
 * Cette logique était écrite DEUX FOIS dans le `<script>` du composant (une
 * fois pour la grille de recos, une fois pour la grille d'épisodes), avec des
 * noms de variables différents et aucun test — les deux copies pouvaient donc
 * diverger sans que rien ne casse. Elle est désormais extraite ici, et ce
 * fichier fige le comportement exact des deux appelants d'origine.
 *
 * Le point a11y à ne jamais perdre (C7) : la région d'annonce reste TOUJOURS
 * dans le DOM et on ne modifie que son `textContent`. Si on la masquait ou la
 * retirait, `aria-live="polite"` n'annoncerait plus rien.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { applyGridFilter } from '../../src/utils/gridFilter';

/** Monte une grille dont les enfants portent `data-search` / `data-types`. */
function mountGrid(cards: { search?: string; types?: string }[]): HTMLElement {
  const ul = document.createElement('ul');
  for (const c of cards) {
    const li = document.createElement('li');
    if (c.search !== undefined) li.dataset.search = c.search;
    if (c.types !== undefined) li.dataset.types = c.types;
    ul.appendChild(li);
  }
  document.body.appendChild(ul);
  return ul;
}

function mountEl(tag = 'p'): HTMLElement {
  const el = document.createElement(tag);
  document.body.appendChild(el);
  return el;
}

/** Styles `display` des enfants, dans l'ordre. */
function displays(grid: HTMLElement): string[] {
  return (Array.from(grid.children) as HTMLElement[]).map((c) => c.style.display);
}

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('applyGridFilter — masquage et comptage', () => {
  it('masque les non-correspondants et laisse les autres au display naturel', () => {
    const grid = mountGrid([{ search: 'parasite' }, { search: 'fez' }]);
    applyGridFilter({
      grid,
      matches: (card) => card.dataset.search === 'parasite',
      emptyMessage: 'Aucun résultat.',
    });
    // Chaîne vide (pas `block`) : on rend la main à la feuille de styles.
    expect(displays(grid)).toEqual(['', 'none']);
  });

  it('retourne le nombre d’éléments visibles', () => {
    const grid = mountGrid([{ search: 'a' }, { search: 'b' }, { search: 'a' }]);
    const n = applyGridFilter({
      grid,
      matches: (card) => card.dataset.search === 'a',
      emptyMessage: 'vide',
    });
    expect(n).toBe(2);
  });

  it('un élément masqué puis re-affiché retrouve son display naturel', () => {
    const grid = mountGrid([{ search: 'parasite' }]);
    applyGridFilter({ grid, matches: () => false, emptyMessage: 'vide' });
    expect(displays(grid)).toEqual(['none']);
    applyGridFilter({ grid, matches: () => true, emptyMessage: 'vide' });
    expect(displays(grid)).toEqual(['']);
  });

  it('ne filtre QUE les enfants directs, pas les descendants profonds', () => {
    const grid = mountGrid([{ search: 'parent' }]);
    const enfant = document.createElement('span');
    enfant.dataset.search = 'enfant';
    grid.children[0].appendChild(enfant);
    applyGridFilter({ grid, matches: () => false, emptyMessage: 'vide' });
    expect((grid.children[0] as HTMLElement).style.display).toBe('none');
    expect(enfant.style.display).toBe('');
  });

  it('applique le prédicat à chaque enfant, dans l’ordre du DOM', () => {
    const grid = mountGrid([{ search: 'a' }, { search: 'b' }, { search: 'c' }]);
    const vus: string[] = [];
    applyGridFilter({
      grid,
      matches: (card) => {
        vus.push(card.dataset.search ?? '');
        return true;
      },
      emptyMessage: 'vide',
    });
    expect(vus).toEqual(['a', 'b', 'c']);
  });

  it('grille vide → 0 visible', () => {
    const grid = mountGrid([]);
    expect(applyGridFilter({ grid, matches: () => true, emptyMessage: 'vide' })).toBe(0);
  });

  it('tous les éléments correspondent → aucun display forcé, 0 masqué', () => {
    const grid = mountGrid([{ search: 'a' }, { search: 'b' }, { search: 'c' }]);
    expect(applyGridFilter({ grid, matches: () => true, emptyMessage: 'vide' })).toBe(3);
    expect(displays(grid)).toEqual(['', '', '']);
  });

  it('aucun élément ne correspond → tous masqués', () => {
    const grid = mountGrid([{ search: 'a' }, { search: 'b' }]);
    expect(applyGridFilter({ grid, matches: () => false, emptyMessage: 'vide' })).toBe(0);
    expect(displays(grid)).toEqual(['none', 'none']);
  });

  it('carte sans `data-search` → le prédicat reçoit `undefined`, sans planter', () => {
    // Cas réel : une carte dont la clé de recherche SSR n'a pas été posée.
    // Les appelants font `card.dataset.search ?? ''` — on vérifie ici que le
    // module transmet bien la carte telle quelle et laisse l'appelant décider.
    const grid = mountGrid([{}, { search: 'parasite' }]);
    const vus: (string | undefined)[] = [];
    const n = applyGridFilter({
      grid,
      matches: (card) => {
        vus.push(card.dataset.search);
        return (card.dataset.search ?? '').includes('para');
      },
      emptyMessage: 'vide',
    });
    expect(vus).toEqual([undefined, 'parasite']);
    expect(n).toBe(1);
    expect(displays(grid)).toEqual(['none', '']);
  });
});

describe('applyGridFilter — région d’annonce (C7)', () => {
  it('écrit le message quand plus rien n’est visible', () => {
    const grid = mountGrid([{ search: 'parasite' }]);
    const status = mountEl();
    applyGridFilter({
      grid,
      status,
      matches: () => false,
      emptyMessage: 'Aucun résultat.',
    });
    expect(status.textContent).toBe('Aucun résultat.');
  });

  it('vide le message dès qu’un résultat réapparaît', () => {
    const grid = mountGrid([{ search: 'parasite' }]);
    const status = mountEl();
    applyGridFilter({ grid, status, matches: () => false, emptyMessage: 'Aucun résultat.' });
    applyGridFilter({ grid, status, matches: () => true, emptyMessage: 'Aucun résultat.' });
    expect(status.textContent).toBe('');
  });

  it('la région reste TOUJOURS dans le DOM et visible (sinon aria-live muet)', () => {
    const grid = mountGrid([{ search: 'parasite' }]);
    const status = mountEl();
    applyGridFilter({ grid, status, matches: () => false, emptyMessage: 'Aucun résultat.' });
    expect(status.isConnected).toBe(true);
    expect(status.hasAttribute('hidden')).toBe(false);
    expect(status.style.display).toBe('');
  });

  it('chaque appelant fournit son propre message', () => {
    const grid = mountGrid([{ search: 'x' }]);
    const status = mountEl();
    applyGridFilter({ grid, status, matches: () => false, emptyMessage: 'Aucun épisode trouvé.' });
    expect(status.textContent).toBe('Aucun épisode trouvé.');
  });

  it('sans région d’annonce, aucun plantage', () => {
    const grid = mountGrid([{ search: 'x' }]);
    expect(() => applyGridFilter({ grid, matches: () => false, emptyMessage: 'vide' })).not.toThrow();
  });
});

describe('applyGridFilter — compteur optionnel', () => {
  it('écrit le nombre visible quand un compteur est fourni', () => {
    const grid = mountGrid([{ search: 'a' }, { search: 'b' }]);
    const counter = mountEl('span');
    applyGridFilter({
      grid,
      counter,
      matches: (card) => card.dataset.search === 'a',
      emptyMessage: 'vide',
    });
    expect(counter.textContent).toBe('1');
  });

  it('écrit « 0 » plutôt que de laisser une valeur périmée', () => {
    const grid = mountGrid([{ search: 'a' }]);
    const counter = mountEl('span');
    counter.textContent = '42';
    applyGridFilter({ grid, counter, matches: () => false, emptyMessage: 'vide' });
    expect(counter.textContent).toBe('0');
  });

  it('sans compteur, aucun plantage', () => {
    const grid = mountGrid([{ search: 'a' }]);
    expect(() => applyGridFilter({ grid, matches: () => true, emptyMessage: 'vide' })).not.toThrow();
  });
});

describe('applyGridFilter — grille absente', () => {
  it('retourne 0 et n’écrit NI le compteur NI la région (comportement d’origine)', () => {
    const status = mountEl();
    const counter = mountEl('span');
    status.textContent = 'inchangé';
    counter.textContent = '7';
    const n = applyGridFilter({
      grid: null,
      status,
      counter,
      matches: () => true,
      emptyMessage: 'Aucun résultat.',
    });
    expect(n).toBe(0);
    expect(status.textContent).toBe('inchangé');
    expect(counter.textContent).toBe('7');
  });

  it('grille undefined → même repli silencieux', () => {
    expect(
      applyGridFilter({ grid: undefined, matches: () => true, emptyMessage: 'vide' }),
    ).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Parité avec les deux appelants d'origine de SourceCatalog.astro
// ---------------------------------------------------------------------------
describe('applyGridFilter — parité avec la grille de recos', () => {
  /** Reproduit `apply()` : filtre par type (chips) ET par texte (fuzzy). */
  function applyRecos(grid: HTMLElement, status: HTMLElement, activeType: string, term: string) {
    return applyGridFilter({
      grid,
      status,
      emptyMessage: 'Aucun résultat.',
      matches: (card) => {
        const okType =
          activeType === 'all' ||
          (card.dataset.types?.split(',').includes(activeType) ?? false);
        const okText = !term || card.dataset.search?.includes(term) === true;
        return okType && okText;
      },
    });
  }

  let grid: HTMLElement;
  let status: HTMLElement;
  beforeEach(() => {
    grid = mountGrid([
      { search: 'parasite bong joon-ho film', types: 'film' },
      { search: 'fez polytron jeu', types: 'jeu' },
      { search: 'dune herbert livre film', types: 'livre,film' },
    ]);
    status = mountEl();
  });

  it('type « all » sans texte → tout visible, aucun message', () => {
    expect(applyRecos(grid, status, 'all', '')).toBe(3);
    expect(displays(grid)).toEqual(['', '', '']);
    expect(status.textContent).toBe('');
  });

  it('une reco multi-types répond à chacun de ses types', () => {
    expect(applyRecos(grid, status, 'film', '')).toBe(2);
    expect(applyRecos(grid, status, 'livre', '')).toBe(1);
  });

  it('type et texte se cumulent', () => {
    expect(applyRecos(grid, status, 'film', 'dune')).toBe(1);
    expect(displays(grid)).toEqual(['none', 'none', '']);
  });

  it('combinaison sans résultat → message « Aucun résultat. »', () => {
    expect(applyRecos(grid, status, 'jeu', 'dune')).toBe(0);
    expect(status.textContent).toBe('Aucun résultat.');
  });
});

describe('applyGridFilter — parité avec la grille d’épisodes', () => {
  /** Reproduit le handler `epSearch` : texte seul + compteur visible. */
  function applyEpisodes(
    grid: HTMLElement,
    counter: HTMLElement,
    status: HTMLElement,
    q: string,
  ) {
    return applyGridFilter({
      grid,
      counter,
      status,
      emptyMessage: 'Aucun épisode trouvé.',
      matches: (card) => !q.trim() || card.dataset.search?.includes(q) === true,
    });
  }

  let grid: HTMLElement;
  let counter: HTMLElement;
  let status: HTMLElement;
  beforeEach(() => {
    grid = mountGrid([
      { search: 'episode douze alice david #12' },
      { search: 'episode vingt-et-un mcfly carlito #21' },
    ]);
    counter = mountEl('span');
    status = mountEl();
  });

  it('requête vide → tous les épisodes, compteur au total', () => {
    expect(applyEpisodes(grid, counter, status, '')).toBe(2);
    expect(counter.textContent).toBe('2');
    expect(status.textContent).toBe('');
  });

  it('requête faite uniquement d’espaces → traitée comme vide', () => {
    expect(applyEpisodes(grid, counter, status, '   ')).toBe(2);
    expect(counter.textContent).toBe('2');
  });

  it('requête filtrante → compteur et grille synchronisés', () => {
    expect(applyEpisodes(grid, counter, status, 'mcfly')).toBe(1);
    expect(counter.textContent).toBe('1');
    expect(displays(grid)).toEqual(['none', '']);
    expect(status.textContent).toBe('');
  });

  it('aucun épisode trouvé → compteur à 0 ET message dédié', () => {
    expect(applyEpisodes(grid, counter, status, 'inexistant')).toBe(0);
    expect(counter.textContent).toBe('0');
    expect(status.textContent).toBe('Aucun épisode trouvé.');
  });
});

describe('applyGridFilter — formatCounter', () => {
  const monter = (n: number) => ({
    grid: mountGrid(Array.from({ length: n }, () => ({}))),
    counter: mountEl('span'),
  });

  it('écrit le nombre seul par défaut', () => {
    const { grid, counter } = monter(3);
    applyGridFilter({ grid, counter, matches: () => true, emptyMessage: '' });
    expect(counter.textContent).toBe('3');
  });

  it('laisse le libellé suivre le nombre', () => {
    // Sans ce point d'extension, le libellé restait figé dans le template et
    // un filtre ramenant le compte à 1 affichait « 1 épisodes ».
    const fmt = (n: number) => `${n} ${n >= 2 ? 'épisodes' : 'épisode'}`;
    const { grid, counter } = monter(3);

    applyGridFilter({ grid, counter, formatCounter: fmt, matches: () => true, emptyMessage: '' });
    expect(counter.textContent).toBe('3 épisodes');

    let vus = 0;
    applyGridFilter({
      grid, counter, formatCounter: fmt, emptyMessage: '',
      matches: () => vus++ === 0,
    });
    expect(counter.textContent).toBe('1 épisode');
  });

  it('accorde aussi zéro au singulier', () => {
    const { grid, counter } = monter(2);
    applyGridFilter({
      grid, counter, emptyMessage: '',
      formatCounter: (n) => `${n} ${n >= 2 ? 'épisodes' : 'épisode'}`,
      matches: () => false,
    });
    expect(counter.textContent).toBe('0 épisode');
  });
});
