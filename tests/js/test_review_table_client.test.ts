// @vitest-environment happy-dom
/**
 * Tests du JS client du tableau de pilotage (tools/review_client_table.js).
 *
 * Même protocole que `test_review_client.test.ts` : les IIFE browser sont
 * évaluées dans happy-dom après avoir posé `window.__recoTestHooks`.
 *
 * On ne charge QUE le core (qui publie `window.__reco`) et le module testé :
 * `review_client_table.js` ne dépend de rien d'autre, et charger le module
 * clavier ferait tenter un `<script src="youtube.com/iframe_api">` que
 * happy-dom refuse bruyamment — du bruit sans valeur de test ici.
 *
 * `fetch` est stubbé : on vérifie ce qui part sur le réseau (route, champs)
 * et ce que le DOM devient au retour — y compris quand le serveur refuse.
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
  tableApplySort: (key: string, dir: string, numeric: boolean) => void;
  tableRowIds: () => string[];
  tableSortByHeader: (th: HTMLElement) => void;
  tableRestoreSort: () => void;
  tableSaveComment: (el: HTMLTextAreaElement) => Promise<any>;
  tableSaveCheck: (el: HTMLInputElement) => Promise<any>;
  tableAcceptType: (el: HTMLInputElement) => Promise<any>;
  tableScheduleSave: (el: HTMLTextAreaElement) => void;
  tableFlushSave: (el: HTMLTextAreaElement) => boolean;
  tableFlushAll: () => void;
  tableNormKey: (s: string) => string;
};

let hooks: Hooks;

beforeAll(() => {
  (window as any).__recoTestHooks = {};
  loadScript('review_client.js');
  loadScript('review_client_table.js');
  hooks = (window as any).__recoTestHooks as Hooks;
});

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '';
});

type RowSpec = {
  id: string;
  title?: string;
  artist?: string;
  links?: string;
  check?: string;
  comment?: string;
  types?: string;
};

function mkRow(spec: RowSpec): string {
  return `<tr class="tbl-row" data-id="${spec.id}"` +
    ` data-k-check="${spec.check ?? '0'}"` +
    ` data-k-title="${spec.title ?? ''}"` +
    ` data-k-artist="${spec.artist ?? ''}"` +
    ` data-k-links="${spec.links ?? '0'}"` +
    ` data-k-comment="${spec.comment ?? ''}"` +
    ` data-k-types="${spec.types ?? ''}">` +
    '<td class="tbl-c-check"><input type="checkbox" class="tbl-check"></td>' +
    '<td class="tbl-c-title">t</td>' +
    '<td class="tbl-c-types">Autre</td>' +
    '<td class="tbl-c-comment"><textarea class="tbl-comment"></textarea></td>' +
    '</tr>';
}

function mountTable(rows: RowSpec[]): void {
  const head = ['check', 'title', 'artist', 'links', 'comment']
    .map((k) => `<th class="tbl-h" data-sort-key="${k}"` +
      ` data-sort-numeric="${k === 'links' || k === 'check' ? '1' : '0'}"` +
      ' aria-sort="none"><button type="button" class="tbl-sort">' +
      `${k}</button></th>`)
    .join('');
  document.body.innerHTML =
    `<table id="reco-table"><thead><tr>${head}</tr></thead>` +
    `<tbody>${rows.map(mkRow).join('')}</tbody></table>` +
    '<div id="toast-zone"></div>';
}

function stubFetch(payload: any, ok = true) {
  const spy = vi.fn().mockImplementation(() => (
    ok
      ? Promise.resolve({ json: () => Promise.resolve(payload) })
      : Promise.reject(new Error('réseau'))
  ));
  (globalThis as any).fetch = spy;
  return spy;
}

function bodyOf(spy: any, call = 0): URLSearchParams {
  return spy.mock.calls[call][1].body as URLSearchParams;
}

describe('tri des colonnes', () => {
  it('trie alphabétiquement, ascendant puis descendant', () => {
    mountTable([
      { id: 'r1', title: 'zebre' },
      { id: 'r2', title: 'brazil' },
      { id: 'r3', title: 'mortel' },
    ]);
    hooks.tableApplySort('title', 'asc', false);
    expect(hooks.tableRowIds()).toEqual(['r2', 'r3', 'r1']);
    hooks.tableApplySort('title', 'desc', false);
    expect(hooks.tableRowIds()).toEqual(['r1', 'r3', 'r2']);
  });

  it('trie numériquement la colonne des liens', () => {
    mountTable([
      { id: 'r1', links: '2' },
      { id: 'r2', links: '10' },
      { id: 'r3', links: '0' },
    ]);
    hooks.tableApplySort('links', 'asc', true);
    // Comparaison numérique, pas lexicographique : 10 après 2.
    expect(hooks.tableRowIds()).toEqual(['r3', 'r1', 'r2']);
  });

  it('garde les cellules vides en bas dans les DEUX sens', () => {
    mountTable([
      { id: 'r1', artist: '' },
      { id: 'r2', artist: 'zoe' },
      { id: 'r3', artist: 'alice' },
    ]);
    hooks.tableApplySort('artist', 'asc', false);
    expect(hooks.tableRowIds()).toEqual(['r3', 'r2', 'r1']);
    hooks.tableApplySort('artist', 'desc', false);
    expect(hooks.tableRowIds()).toEqual(['r2', 'r3', 'r1']);
  });

  it('départage les ex æquo par l’ordre d’origine (chronologique)', () => {
    mountTable([
      { id: 'r1', title: 'meme titre' },
      { id: 'r2', title: 'meme titre' },
      { id: 'r3', title: 'meme titre' },
    ]);
    hooks.tableApplySort('title', 'asc', false);
    expect(hooks.tableRowIds()).toEqual(['r1', 'r2', 'r3']);
    hooks.tableApplySort('title', 'desc', false);
    expect(hooks.tableRowIds()).toEqual(['r1', 'r2', 'r3']);
  });

  it('marque la colonne triée via aria-sort', () => {
    mountTable([{ id: 'r1', title: 'a' }]);
    hooks.tableApplySort('title', 'desc', false);
    const th = document.querySelector('th[data-sort-key="title"]') as HTMLElement;
    const other = document.querySelector('th[data-sort-key="artist"]') as HTMLElement;
    expect(th.getAttribute('aria-sort')).toBe('descending');
    expect(th.classList.contains('tbl-sorted')).toBe(true);
    expect(other.getAttribute('aria-sort')).toBe('none');
  });

  it('un clic sur l’en-tête trie puis inverse, et mémorise le choix', () => {
    mountTable([{ id: 'r1', title: 'b' }, { id: 'r2', title: 'a' }]);
    const th = document.querySelector('th[data-sort-key="title"]') as HTMLElement;
    hooks.tableSortByHeader(th);
    expect(hooks.tableRowIds()).toEqual(['r2', 'r1']);
    expect(JSON.parse(localStorage.getItem('reco-table-sort') as string))
      .toEqual({ key: 'title', dir: 'asc' });
    hooks.tableSortByHeader(th);
    expect(hooks.tableRowIds()).toEqual(['r1', 'r2']);
  });

  it('le clic délégué sur le bouton d’en-tête déclenche le tri', () => {
    mountTable([{ id: 'r1', title: 'b' }, { id: 'r2', title: 'a' }]);
    const btn = document.querySelector(
      'th[data-sort-key="title"] .tbl-sort') as HTMLElement;
    btn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    expect(hooks.tableRowIds()).toEqual(['r2', 'r1']);
  });

  it('restaure le tri mémorisé au chargement', () => {
    localStorage.setItem('reco-table-sort',
      JSON.stringify({ key: 'title', dir: 'desc' }));
    mountTable([{ id: 'r1', title: 'a' }, { id: 'r2', title: 'z' }]);
    hooks.tableRestoreSort();
    expect(hooks.tableRowIds()).toEqual(['r2', 'r1']);
  });

  it('ignore un tri mémorisé illisible ou inconnu', () => {
    localStorage.setItem('reco-table-sort', '{pas du json');
    mountTable([{ id: 'r1', title: 'z' }, { id: 'r2', title: 'a' }]);
    hooks.tableRestoreSort();
    expect(hooks.tableRowIds()).toEqual(['r1', 'r2']);
    localStorage.setItem('reco-table-sort',
      JSON.stringify({ key: 'colonne-fantome', dir: 'asc' }));
    hooks.tableRestoreSort();
    expect(hooks.tableRowIds()).toEqual(['r1', 'r2']);
  });

  it('ne casse pas quand la page n’a pas de tableau', () => {
    document.body.innerHTML = '<p>rien</p>';
    expect(() => hooks.tableApplySort('title', 'asc', false)).not.toThrow();
    expect(() => hooks.tableRestoreSort()).not.toThrow();
    expect(hooks.tableRowIds()).toEqual([]);
  });
});

describe('enregistrement du commentaire et de la coche', () => {
  it('POSTe le commentaire sur /curation et met à jour la clé de tri', async () => {
    mountTable([{ id: 'ubm-1' }]);
    const spy = stubFetch({ kind: 'success', comment: 'Éloge', checked: false });
    const ta = document.querySelector('textarea.tbl-comment') as HTMLTextAreaElement;
    ta.value = 'Éloge';
    await hooks.tableSaveComment(ta);

    expect(spy.mock.calls[0][0]).toBe('/curation');
    expect(bodyOf(spy).get('id')).toBe('ubm-1');
    expect(bodyOf(spy).get('comment')).toBe('Éloge');
    const tr = document.querySelector('tr.tbl-row') as HTMLElement;
    expect(tr.getAttribute('data-k-comment')).toBe('eloge');
    expect((ta.closest('td') as HTMLElement).classList.contains('tbl-saved'))
      .toBe(true);
  });

  it('POSTe la coche et met à jour sa clé de tri', async () => {
    mountTable([{ id: 'ubm-1' }]);
    const spy = stubFetch({ kind: 'success', comment: '', checked: true });
    const box = document.querySelector('input.tbl-check') as HTMLInputElement;
    box.checked = true;
    await hooks.tableSaveCheck(box);

    expect(bodyOf(spy).get('checked')).toBe('1');
    const tr = document.querySelector('tr.tbl-row') as HTMLElement;
    expect(tr.getAttribute('data-k-check')).toBe('1');
  });

  it('envoie checked=0 quand on décoche', async () => {
    mountTable([{ id: 'ubm-1', check: '1' }]);
    const spy = stubFetch({ kind: 'success', comment: '', checked: false });
    const box = document.querySelector('input.tbl-check') as HTMLInputElement;
    box.checked = false;
    await hooks.tableSaveCheck(box);
    expect(bodyOf(spy).get('checked')).toBe('0');
  });

  it('signale un refus du serveur sans perdre la saisie', async () => {
    mountTable([{ id: 'ubm-1' }]);
    stubFetch({ kind: 'error', message: 'Reco introuvable.' });
    const ta = document.querySelector('textarea.tbl-comment') as HTMLTextAreaElement;
    ta.value = 'ma note';
    await hooks.tableSaveComment(ta);

    const cell = ta.closest('td') as HTMLElement;
    expect(cell.classList.contains('tbl-save-error')).toBe(true);
    expect(ta.value).toBe('ma note');
    expect(document.querySelector('.toast')?.textContent)
      .toContain('Reco introuvable.');
  });

  it('survit à un serveur injoignable', async () => {
    mountTable([{ id: 'ubm-1' }]);
    stubFetch(null, false);
    const ta = document.querySelector('textarea.tbl-comment') as HTMLTextAreaElement;
    const res = await hooks.tableSaveComment(ta);
    expect(res).toBeNull();
    expect((ta.closest('td') as HTMLElement).classList
      .contains('tbl-save-error')).toBe(true);
  });

  it('ne poste rien pour un champ hors ligne de tableau', async () => {
    document.body.innerHTML = '<textarea class="tbl-comment"></textarea>';
    const spy = stubFetch({ kind: 'success' });
    const ta = document.querySelector('textarea.tbl-comment') as HTMLTextAreaElement;
    expect(await hooks.tableSaveComment(ta)).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });

  it('la frappe programme une sauvegarde, le blur la déclenche tout de suite',
    async () => {
      vi.useFakeTimers();
      try {
        mountTable([{ id: 'ubm-1' }]);
        const spy = stubFetch({ kind: 'success', comment: 'x', checked: false });
        const ta = document.querySelector(
          'textarea.tbl-comment') as HTMLTextAreaElement;
        ta.value = 'x';
        ta.dispatchEvent(new window.Event('input', { bubbles: true }));
        expect(spy).not.toHaveBeenCalled();     // débattu : rien à la frappe
        ta.dispatchEvent(new window.Event('focusout', { bubbles: true }));
        expect(spy).toHaveBeenCalledTimes(1);   // flush immédiat au blur
        expect(hooks.tableFlushSave(ta)).toBe(false);  // plus rien en attente
      } finally {
        vi.useRealTimers();
      }
    });

  it('la sauvegarde débattue part si on ne quitte pas le champ', async () => {
    vi.useFakeTimers();
    try {
      mountTable([{ id: 'ubm-1' }]);
      const spy = stubFetch({ kind: 'success', comment: 'x', checked: false });
      const ta = document.querySelector(
        'textarea.tbl-comment') as HTMLTextAreaElement;
      hooks.tableScheduleSave(ta);
      hooks.tableScheduleSave(ta);   // une frappe de plus repousse l'échéance
      vi.advanceTimersByTime(1000);
      expect(spy).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('quitter l’onglet enregistre ce qui restait en attente', () => {
    vi.useFakeTimers();
    try {
      mountTable([{ id: 'ubm-1' }, { id: 'ubm-2' }]);
      const spy = stubFetch({ kind: 'success', comment: 'x', checked: false });
      const [a, b] = Array.from(
        document.querySelectorAll('textarea.tbl-comment')) as HTMLTextAreaElement[];
      hooks.tableScheduleSave(a);
      hooks.tableScheduleSave(b);
      hooks.tableFlushAll();
      expect(spy).toHaveBeenCalledTimes(2);
      vi.advanceTimersByTime(2000);
      expect(spy).toHaveBeenCalledTimes(2);  // pas de double envoi ensuite
    } finally {
      vi.useRealTimers();
    }
  });

  it('cocher la case déclenche la sauvegarde par délégation', () => {
    mountTable([{ id: 'ubm-1' }]);
    const spy = stubFetch({ kind: 'success', comment: '', checked: true });
    const box = document.querySelector('input.tbl-check') as HTMLInputElement;
    box.checked = true;
    box.dispatchEvent(new window.Event('change', { bubbles: true }));
    expect(spy.mock.calls[0][0]).toBe('/curation');
  });
});

describe('acceptation d’une proposition de type', () => {
  function mountWithProposal(): HTMLInputElement {
    mountTable([{ id: 'ubm-1', types: 'autre' }]);
    const cell = document.querySelector('.tbl-c-types') as HTMLElement;
    cell.innerHTML += '<label class="tbl-prop"><input type="checkbox" ' +
      'class="tbl-accept" data-id="ubm-1" data-types="film"> → Film</label>';
    return cell.querySelector('input.tbl-accept') as HTMLInputElement;
  }

  it('POSTe l’id seul et réécrit la cellule des types', async () => {
    const box = mountWithProposal();
    const spy = stubFetch({ kind: 'success', types: ['film'], labels: 'Film',
      message: 'Type mis à jour : Film.' });
    await hooks.tableAcceptType(box);

    expect(spy.mock.calls[0][0]).toBe('/accept-type');
    expect(bodyOf(spy).get('id')).toBe('ubm-1');
    expect(bodyOf(spy).get('types')).toBeNull();  // le serveur décide, pas nous
    const cell = document.querySelector('.tbl-c-types') as HTMLElement;
    expect(cell.textContent).toBe('Film');
    const tr = document.querySelector('tr.tbl-row') as HTMLElement;
    expect(tr.getAttribute('data-k-types')).toBe('film');
  });

  it('décoche la case si le serveur refuse', async () => {
    const box = mountWithProposal();
    stubFetch({ kind: 'error', message: 'Aucune proposition.' });
    box.checked = true;
    await hooks.tableAcceptType(box);
    expect(box.checked).toBe(false);
    expect(document.querySelector('.toast')?.textContent)
      .toContain('Aucune proposition.');
  });

  it('décoche la case si le serveur est injoignable', async () => {
    const box = mountWithProposal();
    stubFetch(null, false);
    box.checked = true;
    expect(await hooks.tableAcceptType(box)).toBeNull();
    expect(box.checked).toBe(false);
  });

  it('ignore une case hors ligne de tableau', async () => {
    document.body.innerHTML =
      '<input type="checkbox" class="tbl-accept" data-id="ubm-1">';
    const spy = stubFetch({ kind: 'success' });
    const box = document.querySelector('input.tbl-accept') as HTMLInputElement;
    expect(await hooks.tableAcceptType(box)).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });

  it('cocher « accepter » déclenche le POST par délégation', () => {
    const box = mountWithProposal();
    const spy = stubFetch({ kind: 'success', types: ['film'], labels: 'Film',
      message: 'ok' });
    box.checked = true;
    box.dispatchEvent(new window.Event('change', { bubbles: true }));
    expect(spy.mock.calls[0][0]).toBe('/accept-type');
  });
});

describe('normKey', () => {
  it('reproduit la normalisation serveur (sans accent, minuscules, trim)', () => {
    expect(hooks.tableNormKey('  Éloge de la Fuite ')).toBe('eloge de la fuite');
    expect(hooks.tableNormKey('')).toBe('');
  });
});
