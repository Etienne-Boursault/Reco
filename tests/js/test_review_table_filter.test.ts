// @vitest-environment happy-dom
/**
 * Tests du filtre par épisode (tools/review_client_filter.js).
 *
 * Le point qui compte : le filtre MASQUE, le tri RÉORDONNE. Les deux doivent
 * se composer sans se connaître — d'où les tests de coexistence en fin de
 * fichier, qui chargent AUSSI le module de tri.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const TOOLS = path.resolve(__dirname, '../../tools');

function loadScript(name: string): void {
  const code = readFileSync(path.join(TOOLS, name), 'utf-8');
  // eslint-disable-next-line no-new-func -- évaluation volontaire de l'IIFE
  new Function(code)();
}

type Hooks = {
  filterMount: () => void;
  filterApply: (guid: string) => number;
  filterReadStored: () => string;
  filterStore: (guid: string) => void;
  tableApplySort: (key: string, dir: string, numeric: boolean) => void;
  tableRowIds: () => string[];
};

let hooks: Hooks;

beforeAll(() => {
  (window as any).__recoTestHooks = {};
  loadScript('review_client.js');
  loadScript('review_client_table.js');
  loadScript('review_client_filter.js');
  hooks = (window as any).__recoTestHooks as Hooks;
});

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '';
});

type Row = { id: string; ep: string; title?: string };

function mount(rows: Row[], episodes: string[]): void {
  const options = episodes
    .map((g) => `<option value="${g}">${g} (n)</option>`).join('');
  const trs = rows.map((r) =>
    `<tr class="tbl-row" data-id="${r.id}" data-ep="${r.ep}"` +
    ` data-k-title="${r.title ?? r.id}">` +
    `<td class="tbl-c-title">${r.title ?? r.id}</td>` +
    '<td class="tbl-c-check"><input type="checkbox" class="tbl-check"></td>' +
    '</tr>').join('');
  document.body.innerHTML =
    '<div class="tbl-bar">' +
    '<select id="tbl-filter-ep" class="tbl-filter">' +
    `<option value="">Tous</option>${options}</select>` +
    '<button type="button" id="tbl-filter-clear" hidden>✕</button>' +
    '<span id="tbl-filter-count"></span></div>' +
    `<table id="reco-table"><tbody>${trs}</tbody></table>` +
    '<div id="toast-zone"></div>';
}

const JEU: Row[] = [
  { id: 'ubm-1', ep: 'g1', title: 'alpha' },
  { id: 'ubm-2', ep: 'g1', title: 'charlie' },
  { id: 'ubm-3', ep: 'g2', title: 'bravo' },
];

const visibles = () => Array
  .from(document.querySelectorAll('#reco-table tbody tr.tbl-row'))
  .filter((tr) => !(tr as HTMLElement).hidden)
  .map((tr) => (tr as HTMLElement).dataset.id);

const select = () => document.getElementById('tbl-filter-ep') as HTMLSelectElement;
const clearBtn = () => document.getElementById('tbl-filter-clear') as HTMLElement;
const count = () => document.getElementById('tbl-filter-count') as HTMLElement;

// ---------------------------------------------------------------------------
// apply
// ---------------------------------------------------------------------------
describe('apply', () => {
  it('ne garde que les lignes de l’épisode choisi', () => {
    mount(JEU, ['g1', 'g2']);
    expect(hooks.filterApply('g1')).toBe(2);
    expect(visibles()).toEqual(['ubm-1', 'ubm-2']);
  });

  it('un guid vide réaffiche tout', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.filterApply('g1');
    expect(hooks.filterApply('')).toBe(3);
    expect(visibles()).toEqual(['ubm-1', 'ubm-2', 'ubm-3']);
  });

  it('masque par l’attribut `hidden`, pas en retirant du DOM', () => {
    // Une ligne retirée perdrait son commentaire en cours de frappe et son
    // rang de tri. `hidden` est aussi sémantique pour les lecteurs d'écran.
    mount(JEU, ['g1', 'g2']);
    hooks.filterApply('g2');
    const toutes = document.querySelectorAll('#reco-table tbody tr.tbl-row');
    expect(toutes).toHaveLength(3);
    expect((toutes[0] as HTMLElement).hidden).toBe(true);
    expect((toutes[0] as HTMLElement).style.display).toBe('');
  });

  it('un guid inconnu ne masque pas tout en silence — il renvoie 0', () => {
    mount(JEU, ['g1', 'g2']);
    expect(hooks.filterApply('fantome')).toBe(0);
  });

  it('affiche le compte filtré, et rien quand tout est affiché', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.filterApply('g1');
    expect(count().textContent).toBe('2 recos sur 3');
    hooks.filterApply('g2');
    expect(count().textContent).toBe('1 reco sur 3');   // singulier
    hooks.filterApply('');
    expect(count().textContent).toBe('');
  });

  it('le bouton « tout afficher » n’apparaît que filtre actif', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.filterApply('g1');
    expect(clearBtn().hidden).toBe(false);
    hooks.filterApply('');
    expect(clearBtn().hidden).toBe(true);
  });

  it('tolère une page sans compteur ni bouton', () => {
    document.body.innerHTML =
      '<table id="reco-table"><tbody>' +
      '<tr class="tbl-row" data-id="a" data-ep="g1"></tr></tbody></table>';
    expect(() => hooks.filterApply('g1')).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Persistance
// ---------------------------------------------------------------------------
describe('persistance', () => {
  it('aller-retour, et le vide efface la clé', () => {
    hooks.filterStore('g1');
    expect(hooks.filterReadStored()).toBe('g1');
    hooks.filterStore('');
    expect(hooks.filterReadStored()).toBe('');
  });

  it('navigation privée : le filtre marche, il n’est juste pas mémorisé', () => {
    // Les stubs vont sur l'INSTANCE, pas sur `Storage.prototype` : happy-dom
    // pose ces méthodes en propriétés propres, et substituer le prototype
    // n'intercepte donc rien — le test passait alors sans rien prouver.
    const set = vi.spyOn(window.localStorage, 'setItem')
      .mockImplementation(() => { throw new Error('QuotaExceededError'); });
    const get = vi.spyOn(window.localStorage, 'getItem')
      .mockImplementation(() => { throw new Error('accès refusé'); });
    try {
      expect(() => hooks.filterStore('g1')).not.toThrow();
      expect(set).toHaveBeenCalled();          // le stub a bien intercepté
      expect(hooks.filterReadStored()).toBe('');
      expect(get).toHaveBeenCalled();
    } finally {
      set.mockRestore();
      get.mockRestore();
    }
  });

  it('effacer le filtre survit à un storage en lecture seule', () => {
    const rm = vi.spyOn(window.localStorage, 'removeItem')
      .mockImplementation(() => { throw new Error('QuotaExceededError'); });
    try {
      expect(() => hooks.filterStore('')).not.toThrow();
      expect(rm).toHaveBeenCalled();
    } finally {
      rm.mockRestore();
    }
  });
});

// ---------------------------------------------------------------------------
// mount
// ---------------------------------------------------------------------------
describe('mount', () => {
  it('sans tableau sur la page, ne lève rien', () => {
    document.body.innerHTML = '<p>rien ici</p>';
    expect(() => hooks.filterMount()).not.toThrow();
  });

  it('restaure le filtre mémorisé', () => {
    hooks.filterStore('g2');
    mount(JEU, ['g1', 'g2']);
    hooks.filterMount();
    expect(select().value).toBe('g2');
    expect(visibles()).toEqual(['ubm-3']);
  });

  it('un épisode mémorisé qui a DISPARU ne masque pas tout', () => {
    // Sinon la page s'ouvre vide, sans rien expliquer — et l'utilisateur croit
    // le tableau cassé. Le filtre périmé est effacé, pas appliqué.
    hooks.filterStore('g-supprime');
    mount(JEU, ['g1', 'g2']);
    hooks.filterMount();
    expect(visibles()).toHaveLength(3);
    expect(hooks.filterReadStored()).toBe('');
  });

  it('changer la sélection filtre et mémorise', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.filterMount();
    select().value = 'g1';
    select().dispatchEvent(new window.Event('change', { bubbles: true }));
    expect(visibles()).toEqual(['ubm-1', 'ubm-2']);
    expect(hooks.filterReadStored()).toBe('g1');
  });

  it('le bouton « tout afficher » remet à zéro et oublie le choix', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.filterMount();
    select().value = 'g1';
    select().dispatchEvent(new window.Event('change', { bubbles: true }));
    clearBtn().dispatchEvent(new window.Event('click', { bubbles: true }));
    expect(select().value).toBe('');
    expect(visibles()).toHaveLength(3);
    expect(hooks.filterReadStored()).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Coexistence avec le tri — LE point de conception
// ---------------------------------------------------------------------------
describe('filtre et tri se composent', () => {
  it('trier ne révèle pas une ligne filtrée', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.filterApply('g1');
    hooks.tableApplySort('title', 'asc', false);
    expect(visibles()).toEqual(['ubm-1', 'ubm-2']);
    expect((document.querySelector('[data-id="ubm-3"]') as HTMLElement).hidden)
      .toBe(true);
  });

  it('filtrer ne perturbe pas l’ordre de tri en place', () => {
    mount(JEU, ['g1', 'g2']);
    hooks.tableApplySort('title', 'asc', false);
    const ordreTrie = hooks.tableRowIds();     // alpha, bravo, charlie
    hooks.filterApply('g1');
    expect(hooks.tableRowIds()).toEqual(ordreTrie);
    expect(visibles()).toEqual(['ubm-1', 'ubm-2']);
  });
});
