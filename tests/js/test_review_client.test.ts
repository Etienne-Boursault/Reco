// @vitest-environment happy-dom
/**
 * Tests du JS client du review_server (M5 CR cumulative).
 *
 * Les fichiers tools/review_client*.js sont des IIFE browser : on les évalue
 * dans happy-dom après avoir posé `window.__recoTestHooks` — chaque IIFE y
 * publie alors ses helpers testables (jamais exposés en prod, le hook n'y
 * existe pas). L'ordre de chargement reproduit la concaténation serveur
 * (review_render_common._CLIENT_JS_FILES) : core d'abord (publie
 * window.__reco), puis les modules qui le consomment.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';

const TOOLS = path.resolve(__dirname, '../../tools');

function loadScript(name: string): void {
  const code = readFileSync(path.join(TOOLS, name), 'utf-8');
  // eslint-disable-next-line no-new-func -- évaluation volontaire de l'IIFE
  new Function(code)();
}

type Hooks = {
  clearEditParamFromUrl: () => void;
  applySearchFilter: (q: string) => void;
  getRows: (includeDiscarded: boolean) => HTMLElement[];
  normText: (s: string) => string;
  rowStatus: (li: HTMLElement) => string;
  rowTitle: (li: HTMLElement) => string;
  applySort: (mode: string) => void;
  getSortableItems: (ul: HTMLElement) => HTMLElement[];
  TODO_RANK: Record<string, number>;
  DONE_RANK: Record<string, number>;
};

let hooks: Hooks;

beforeAll(() => {
  (window as any).__recoTestHooks = {};
  loadScript('review_client.js');
  loadScript('review_client_cluster.js');
  loadScript('review_client_keyboard.js');
  loadScript('review_client_toolbar.js');
  hooks = (window as any).__recoTestHooks as Hooks;
});

function mkRow(id: string, cls: string, title: string): string {
  return `<li class="row ${cls}" data-reco-id="${id}"><div class="hd">` +
    `<span class="type"><span class="type-emoji" title="Film">🎬</span></span>` +
    `<b>${title}</b></div></li>`;
}

function mountEpisode(rowsHtml: string): HTMLElement {
  document.body.innerHTML =
    `<section class="ep"><ul>${rowsHtml}` +
    `<li class="row add-reco-row">+ Ajouter</li></ul></section>`;
  return document.querySelector('section.ep ul') as HTMLElement;
}

describe('namespace partagé', () => {
  it('le core publie initOnReady et toast, le keyboard publie setActiveRow', () => {
    const ns = (window as any).__reco;
    expect(typeof ns.initOnReady).toBe('function');
    expect(typeof ns.toast).toBe('function');
    expect(typeof ns.setActiveRow).toBe('function');
  });
});

describe('normText', () => {
  it('retire les accents et met en minuscules', () => {
    expect(hooks.normText('Éloge de la Fuite')).toBe('eloge de la fuite');
  });
  it('trim les espaces', () => {
    expect(hooks.normText('  Brazil  ')).toBe('brazil');
  });
});

describe('rowStatus (dont guestwork — N3 CR)', () => {
  const cases: Array<[string, string]> = [
    ['done', 'done'],
    ['done citation', 'citation'],
    ['done guestwork', 'done'],
    ['discarded', 'discarded'],
    ['cluster', 'cluster'],
    ['', 'draft'],
  ];
  for (const [cls, expected] of cases) {
    it(`classe "${cls}" → ${expected}`, () => {
      const ul = mountEpisode(mkRow('r1', cls, 'T'));
      const li = ul.querySelector('li.row') as HTMLElement;
      expect(hooks.rowStatus(li)).toBe(expected);
    });
  }
  it('TODO_RANK et DONE_RANK connaissent la clé guestwork (défensif)', () => {
    expect(hooks.TODO_RANK.guestwork).toBeTypeOf('number');
    expect(hooks.DONE_RANK.guestwork).toBeTypeOf('number');
  });
});

describe('applySort', () => {
  function ids(): string[] {
    return Array.from(
      document.querySelectorAll('li.row[data-reco-id]'),
    ).map((li) => (li as HTMLElement).dataset.recoId as string);
  }

  it('alpha : trie par titre normalisé, add-reco-row reste en dernier', () => {
    mountEpisode(
      mkRow('r1', '', 'Zebra') + mkRow('r2', '', 'Éloge') + mkRow('r3', '', 'brazil'),
    );
    hooks.applySort('alpha');
    expect(ids()).toEqual(['r3', 'r2', 'r1']);
    const items = Array.from(document.querySelectorAll('section.ep ul > li'));
    expect((items.at(-1) as HTMLElement).className).toContain('add-reco-row');
  });

  it('todo : drafts et clusters avant les traités, discarded en dernier', () => {
    mountEpisode(
      mkRow('r1', 'done', 'A') + mkRow('r2', '', 'B') +
      mkRow('r3', 'discarded', 'C') + mkRow('r4', 'cluster', 'D'),
    );
    hooks.applySort('todo');
    const order = ids();
    expect(order.indexOf('r2')).toBeLessThan(order.indexOf('r1'));
    expect(order.indexOf('r4')).toBeLessThan(order.indexOf('r1'));
    expect(order.at(-1)).toBe('r3');
  });

  it('done : les traités (dont guestwork validé) d’abord', () => {
    mountEpisode(
      mkRow('r1', '', 'A') + mkRow('r2', 'done guestwork', 'B') +
      mkRow('r3', 'done citation', 'C'),
    );
    hooks.applySort('done');
    const order = ids();
    expect(order.indexOf('r2')).toBeLessThan(order.indexOf('r1'));
    expect(order.indexOf('r3')).toBeLessThan(order.indexOf('r1'));
  });

  it('chrono : restaure l’ordre initial capturé (origIdx)', () => {
    mountEpisode(mkRow('r1', '', 'B') + mkRow('r2', '', 'A'));
    hooks.applySort('alpha');
    expect(ids()).toEqual(['r2', 'r1']);
    hooks.applySort('chrono');
    expect(ids()).toEqual(['r1', 'r2']);
  });
});

describe('applySearchFilter', () => {
  it('masque les cartes sans correspondance (insensible à la casse)', () => {
    mountEpisode(mkRow('r1', '', 'Brazil') + mkRow('r2', '', 'Le Parrain'));
    hooks.applySearchFilter('brazil');
    const r1 = document.querySelector('[data-reco-id="r1"]') as HTMLElement;
    const r2 = document.querySelector('[data-reco-id="r2"]') as HTMLElement;
    expect(r1.classList.contains('hidden-by-search')).toBe(false);
    expect(r2.classList.contains('hidden-by-search')).toBe(true);
  });
  it('requête vide → tout réaffiché', () => {
    mountEpisode(mkRow('r1', '', 'Brazil') + mkRow('r2', '', 'Le Parrain'));
    hooks.applySearchFilter('brazil');
    hooks.applySearchFilter('');
    expect(document.querySelectorAll('.hidden-by-search').length).toBe(0);
  });
});

describe('clearEditParamFromUrl (#4)', () => {
  it('retire ?edit= en préservant les autres paramètres', () => {
    window.history.replaceState({}, '', '/ep?guid=g1&edit=ubm-0001');
    hooks.clearEditParamFromUrl();
    expect(window.location.search).toContain('guid=g1');
    expect(window.location.search).not.toContain('edit=');
  });
  it('no-op quand edit est absent', () => {
    window.history.replaceState({}, '', '/ep?guid=g2');
    hooks.clearEditParamFromUrl();
    expect(window.location.search).toBe('?guid=g2');
  });
});
