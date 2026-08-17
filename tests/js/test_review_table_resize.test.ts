// @vitest-environment happy-dom
/**
 * Tests du redimensionnement des colonnes (tools/review_client_resize.js).
 *
 * Même protocole que les autres modules client : l'IIFE est évaluée dans
 * happy-dom après avoir posé `window.__recoTestHooks`.
 *
 * happy-dom NE FAIT PAS DE MISE EN PAGE : `getBoundingClientRect()` y renvoie
 * des zéros. Les largeurs mesurées sont donc simulées explicitement, ce qui est
 * suffisant — ce module ne calcule pas de mise en page, il lit une largeur,
 * applique un delta et écrit le résultat. C'est cette chaîne qu'on teste.
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
  resizeMount: () => void;
  resizeClamp: (px: number) => number;
  resizeReadStored: () => Record<string, number>;
  resizeStore: (w: Record<string, number>) => void;
  resizeReset: (table: HTMLElement, th: HTMLElement) => void;
  resizeFreeze: (table: HTMLElement) => void;
  resizeApplyWidth: (t: HTMLElement, th: HTMLElement, px: number) => number;
  resizeRestore: (table: HTMLElement) => void;
  RESIZE_MIN_W: number;
  RESIZE_MAX_W: number;
  RESIZE_STEP: number;
};

let hooks: Hooks;

beforeAll(() => {
  (window as any).__recoTestHooks = {};
  loadScript('review_client.js');
  loadScript('review_client_resize.js');
  hooks = (window as any).__recoTestHooks as Hooks;
});

const COLS = ['check', 'title', 'artist', 'links'];

/** Largeur simulée par colonne — happy-dom ne met rien en page. */
function fakeWidths(px: Record<string, number>): void {
  for (const th of Array.from(document.querySelectorAll('thead th'))) {
    const key = (th as HTMLElement).dataset.sortKey as string;
    (th as any).getBoundingClientRect = () => ({ width: px[key] ?? 100 });
  }
}

function mountTable(): HTMLTableElement {
  const head = COLS.map((k) =>
    `<th class="tbl-h" data-sort-key="${k}" aria-sort="none">` +
    `<button type="button" class="tbl-sort">${k}</button>` +
    `<span class="tbl-resize" role="separator" tabindex="0"` +
    ` data-resize-key="${k}"></span></th>`).join('');
  document.body.innerHTML =
    `<table id="reco-table"><thead><tr>${head}</tr></thead>` +
    '<tbody><tr class="tbl-row" data-id="ubm-1"><td>x</td></tr></tbody></table>';
  fakeWidths({ check: 40, title: 300, artist: 120, links: 200 });
  return document.getElementById('reco-table') as HTMLTableElement;
}

const th = (key: string) =>
  document.querySelector(`th[data-sort-key="${key}"]`) as HTMLElement;
const handle = (key: string) =>
  document.querySelector(`.tbl-resize[data-resize-key="${key}"]`) as HTMLElement;

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '';
});

// ---------------------------------------------------------------------------
// clamp — les bornes
// ---------------------------------------------------------------------------
describe('clamp', () => {
  it('refuse de descendre sous le minimum lisible', () => {
    expect(hooks.resizeClamp(-500)).toBe(hooks.RESIZE_MIN_W);
    expect(hooks.resizeClamp(0)).toBe(hooks.RESIZE_MIN_W);
  });

  it('plafonne un glissement parti trop loin', () => {
    expect(hooks.resizeClamp(99999)).toBe(hooks.RESIZE_MAX_W);
  });

  it('arrondit au pixel — pas de largeur à 12 décimales dans le storage', () => {
    expect(hooks.resizeClamp(120.4)).toBe(120);
    expect(hooks.resizeClamp(120.6)).toBe(121);
  });

  it('laisse passer une valeur normale', () => {
    expect(hooks.resizeClamp(250)).toBe(250);
  });
});

// ---------------------------------------------------------------------------
// Persistance
// ---------------------------------------------------------------------------
describe('persistance des largeurs', () => {
  it('aller-retour par localStorage', () => {
    hooks.resizeStore({ title: 320 });
    expect(hooks.resizeReadStored()).toEqual({ title: 320 });
  });

  it('storage vide ou illisible → objet vide, jamais une exception', () => {
    expect(hooks.resizeReadStored()).toEqual({});
    localStorage.setItem('reco-table-widths', 'pas du json{');
    expect(hooks.resizeReadStored()).toEqual({});
    localStorage.setItem('reco-table-widths', '"une chaine"');
    expect(hooks.resizeReadStored()).toEqual({});
    localStorage.setItem('reco-table-widths', 'null');
    expect(hooks.resizeReadStored()).toEqual({});
  });

  it('navigation privée : l’écriture échoue sans casser le redimensionnement', () => {
    // Le stub va sur l'INSTANCE, pas sur `Storage.prototype` : happy-dom pose
    // ces méthodes en propriétés propres, et substituer le prototype
    // n'intercepte rien — ce test passait alors sans rien prouver.
    const set = vi.spyOn(window.localStorage, 'setItem')
      .mockImplementation(() => { throw new Error('QuotaExceededError'); });
    try {
      const table = mountTable();
      expect(() => hooks.resizeApplyWidth(table, th('title'), 400)).not.toThrow();
      expect(set).toHaveBeenCalled();                  // le stub a intercepté
      expect(th('title').style.width).toBe('400px');   // la largeur s'applique
    } finally {
      set.mockRestore();
    }
  });
});

// ---------------------------------------------------------------------------
// freeze — le passage en largeurs explicites
// ---------------------------------------------------------------------------
describe('freeze', () => {
  it('fige les largeurs mesurées de TOUTES les colonnes, pas seulement une', () => {
    const table = mountTable();
    hooks.resizeFreeze(table);
    expect(th('check').style.width).toBe('40px');
    expect(th('title').style.width).toBe('300px');
    expect(th('artist').style.width).toBe('120px');
    expect(th('links').style.width).toBe('200px');
  });

  it('bascule la table en table-layout:fixed', () => {
    const table = mountTable();
    expect(table.style.tableLayout).toBe('');
    hooks.resizeFreeze(table);
    expect(table.style.tableLayout).toBe('fixed');
    expect(table.dataset.widthsFrozen).toBe('1');
  });

  it('est idempotent : refiger n’écrase pas une largeur déjà choisie', () => {
    const table = mountTable();
    hooks.resizeApplyWidth(table, th('title'), 500);
    // La mesure simulée dit toujours 300 : si freeze re-mesurait, on la perdrait.
    hooks.resizeFreeze(table);
    expect(th('title').style.width).toBe('500px');
  });

  it('applique les bornes aux largeurs mesurées', () => {
    const table = mountTable();
    fakeWidths({ check: 5, title: 99999, artist: 120, links: 200 });
    hooks.resizeFreeze(table);
    expect(th('check').style.width).toBe(hooks.RESIZE_MIN_W + 'px');
    expect(th('title').style.width).toBe(hooks.RESIZE_MAX_W + 'px');
  });
});

// ---------------------------------------------------------------------------
// applyWidth / restore
// ---------------------------------------------------------------------------
describe('applyWidth', () => {
  it('pose la largeur, la mémorise, et fige la table au passage', () => {
    const table = mountTable();
    expect(hooks.resizeApplyWidth(table, th('title'), 420)).toBe(420);
    expect(th('title').style.width).toBe('420px');
    expect(table.style.tableLayout).toBe('fixed');
  });

  it('ne mémorise QUE les colonnes réellement ajustées', () => {
    // `freeze` pose une largeur sur les quatre colonnes, mais seule celle que
    // l'utilisateur a bougée est retenue. Les autres restent libres de suivre
    // la largeur de la fenêtre au prochain chargement — mémoriser une mesure
    // faite sur un écran donné la figerait sur tous les autres.
    const table = mountTable();
    hooks.resizeApplyWidth(table, th('title'), 420);
    expect(hooks.resizeReadStored()).toEqual({ title: 420 });
    expect(th('artist').style.width).toBe('120px');   // figée, non mémorisée
  });

  it('ne touche PAS aux <td> : seule la première rangée dicte en layout fixed', () => {
    const table = mountTable();
    hooks.resizeApplyWidth(table, th('title'), 420);
    const td = table.querySelector('tbody td') as HTMLElement;
    expect(td.style.width).toBe('');
  });
});

describe('restore', () => {
  it('sans rien de mémorisé, laisse l’ajustement automatique intact', () => {
    const table = mountTable();
    hooks.resizeRestore(table);
    expect(table.style.tableLayout).toBe('');
    expect(th('title').style.width).toBe('');
  });

  it('réapplique les largeurs mémorisées', () => {
    hooks.resizeStore({ title: 333 });
    const table = mountTable();
    hooks.resizeRestore(table);
    expect(th('title').style.width).toBe('333px');
    expect(table.style.tableLayout).toBe('fixed');
  });

  it('ignore une valeur corrompue sans perdre les autres', () => {
    hooks.resizeStore({ title: 333, artist: 'large' as any, links: NaN as any });
    const table = mountTable();
    hooks.resizeRestore(table);
    expect(th('title').style.width).toBe('333px');
    // Les colonnes invalides gardent la largeur figée à la mesure.
    expect(th('artist').style.width).toBe('120px');
    expect(th('links').style.width).toBe('200px');
  });
});

// ---------------------------------------------------------------------------
// reset
// ---------------------------------------------------------------------------
describe('reset', () => {
  it('la DERNIÈRE largeur retirée rend la main à l’ajustement automatique', () => {
    const table = mountTable();
    hooks.resizeApplyWidth(table, th('title'), 420);
    hooks.resizeReset(table, th('title'));
    expect(hooks.resizeReadStored()).toEqual({});
    expect(table.style.tableLayout).toBe('');
    expect(table.dataset.widthsFrozen).toBeUndefined();
    // Toutes les colonnes, y compris celles figées par `freeze`, sont rendues.
    for (const k of COLS) expect(th(k).style.width).toBe('');
  });

  it('tant qu’il reste des colonnes réglées, la table demeure figée', () => {
    const table = mountTable();
    hooks.resizeApplyWidth(table, th('title'), 420);
    hooks.resizeApplyWidth(table, th('artist'), 90);
    hooks.resizeReset(table, th('title'));
    expect(table.style.tableLayout).toBe('fixed');
    expect(hooks.resizeReadStored()).toEqual({ artist: 90 });
    // La colonne rendue ne reste ni vide ni à zéro : elle sauterait à 0px,
    // le layout fixed ne lui donnant aucune largeur de repli.
    expect(th('title').style.width).not.toBe('');
    expect(th('title').style.width).not.toBe('0px');
  });
});

// ---------------------------------------------------------------------------
// Interaction — LE piège : ne pas déclencher le tri
// ---------------------------------------------------------------------------
describe('la poignée n’active jamais le tri', () => {
  function pointerDownSurPoignee(key: string): { defaultPrevented: boolean } {
    const ev = new window.Event('pointerdown', {
      bubbles: true, cancelable: true,
    }) as any;
    ev.button = 0;
    ev.clientX = 500;
    ev.pointerId = 1;
    handle(key).dispatchEvent(ev);
    return ev;
  }

  it('le pointerdown est stoppé net (preventDefault + pas de propagation)', () => {
    const table = mountTable();
    hooks.resizeMount();
    const vuParLeTableau = vi.fn();
    // Écouteur posé APRÈS le sien, sur le même nœud : `stopPropagation` ne
    // l'atteindrait pas. On écoute donc sur un ancêtre, ce que fait vraiment
    // le tri (délégation depuis document).
    document.addEventListener('pointerdown', vuParLeTableau);
    const ev = pointerDownSurPoignee('title');
    document.removeEventListener('pointerdown', vuParLeTableau);
    expect(ev.defaultPrevented).toBe(true);
    expect(vuParLeTableau).not.toHaveBeenCalled();
    expect(table).toBeTruthy();
  });

  it('un clic sur le BOUTON de tri passe toujours', () => {
    mountTable();
    hooks.resizeMount();
    const vu = vi.fn();
    document.addEventListener('pointerdown', vu);
    const ev = new window.Event('pointerdown', { bubbles: true, cancelable: true }) as any;
    ev.button = 0;
    (document.querySelector('.tbl-sort') as HTMLElement).dispatchEvent(ev);
    document.removeEventListener('pointerdown', vu);
    expect(vu).toHaveBeenCalledTimes(1);
    expect(ev.defaultPrevented).toBe(false);
  });

  it('le clic droit sur la poignée ne démarre pas de glissement', () => {
    mountTable();
    hooks.resizeMount();
    const ev = new window.Event('pointerdown', { bubbles: true, cancelable: true }) as any;
    ev.button = 2;
    handle('title').dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Clavier — la page se pilote sans souris, la largeur aussi
// ---------------------------------------------------------------------------
describe('clavier', () => {
  function touche(key: string, k: string): void {
    handle(key).dispatchEvent(
      new window.KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
  }

  it('flèche droite élargit, flèche gauche rétrécit, du pas défini', () => {
    const table = mountTable();
    hooks.resizeMount();
    touche('title', 'ArrowRight');
    expect(th('title').style.width).toBe((300 + hooks.RESIZE_STEP) + 'px');
    // La mesure simulée reste à 300 : on repart d'elle, pas du cumul.
    touche('title', 'ArrowLeft');
    expect(th('title').style.width).toBe((300 - hooks.RESIZE_STEP) + 'px');
    expect(table.style.tableLayout).toBe('fixed');
  });

  it('Home et Échap réinitialisent la colonne', () => {
    const table = mountTable();
    hooks.resizeMount();
    hooks.resizeApplyWidth(table, th('title'), 420);
    touche('title', 'Home');
    expect(hooks.resizeReadStored().title).toBeUndefined();
    hooks.resizeApplyWidth(table, th('artist'), 90);
    touche('artist', 'Escape');
    expect(hooks.resizeReadStored().artist).toBeUndefined();
  });

  it('une touche sans rapport ne change rien', () => {
    mountTable();
    hooks.resizeMount();
    touche('title', 'a');
    expect(th('title').style.width).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Montage
// ---------------------------------------------------------------------------
describe('montage', () => {
  it('sans tableau sur la page, ne lève rien', () => {
    document.body.innerHTML = '<p>pas de tableau ici</p>';
    expect(() => hooks.resizeMount()).not.toThrow();
  });

  it('réapplique les largeurs mémorisées dès le montage', () => {
    hooks.resizeStore({ artist: 77 });
    mountTable();
    hooks.resizeMount();
    expect(th('artist').style.width).toBe('77px');
  });

  it('double-clic sur la poignée réinitialise la colonne', () => {
    const table = mountTable();
    hooks.resizeMount();
    hooks.resizeApplyWidth(table, th('title'), 420);
    handle('title').dispatchEvent(
      new window.Event('dblclick', { bubbles: true, cancelable: true }));
    expect(hooks.resizeReadStored().title).toBeUndefined();
  });
});
