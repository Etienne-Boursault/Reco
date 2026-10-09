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
  rowState: (li: HTMLElement) => string;
  nextPending: (id: string) => HTMLElement | null;
  updateEnd: () => boolean;
  filterEpisodes: (q: string) => void;
  initFocus: () => void;
};

let hooks: Hooks;

beforeAll(() => {
  (window as any).__recoTestHooks = {};
  loadScript('review_client.js');
  loadScript('review_client_cluster.js');
  loadScript('review_client_keyboard.js');
  loadScript('review_client_focus.js');
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

// Mode focus (/ep) : liste de l'épisode + une carte à la fois.
function mountFocus(rows: Array<[string, string, string]>): void {
  const items = rows.map(([id, , title], i) =>
    `<li><button type="button" class="fx-item" data-state="${rows[i][1].includes('done') ? 'done' : (rows[i][1] === 'discarded' ? 'discarded' : 'draft')}" ` +
    `data-fx-target="${id}" data-time="00:0${i}:00"><span class="fx-t">${title}</span>` +
    `<span class="fx-m"></span><span class="fx-sig">!</span></button></li>`).join('');
  const cards = rows.map(([id, cls, title]) =>
    `<li class="row ${cls}" data-reco-id="${id}" data-signals="1"><div class="hd"><b>${title}</b></div>` +
    `<form method="post" action="/save"><input type="hidden" name="id" value="${id}">` +
    `<label><input type="checkbox" name="who" value="Carla"></label>` +
    `<label><input type="checkbox" name="who" value="Carla de Coignac"></label>` +
    `<input type="text" name="other" value="">` +
    `<button type="submit" name="action" value="validate">Valider</button>` +
    `<button type="submit" name="action" value="guest-work">Leur œuvre</button>` +
    `</form></li>`).join('');
  document.body.innerHTML =
    `<div class="focus" data-focus><div class="fx-progress"><b data-fx-done>0</b>` +
    `<span data-fx-bar></span></div><nav data-fx-list><button data-fx-list-toggle>` +
    `Reco <span data-fx-pos>1</span></button><ol>${items}</ol></nav>` +
    `<section class="ep"><div class="fx-end" data-fx-end hidden>` +
    `<b data-fx-count="done">0</b><span data-one="validée" data-many="validées"></span>` +
    `<button data-fx-again>Revoir</button></div><ul>${cards}</ul></section></div>` +
    `<div id="toast-zone"></div>`;
  hooks.initFocus();
}

function fire(name: string, detail: object): void {
  document.dispatchEvent(new CustomEvent(name, { detail }));
}

function activeId(): string {
  const li = document.querySelector('li.row.active') as HTMLElement | null;
  return li ? (li.dataset.recoId as string) : '';
}

describe('rowState (même partition que le serveur)', () => {
  const cases: Array<[string, string]> = [
    ['done', 'done'],
    ['done citation', 'citation'],
    ['done guestwork', 'guestwork'],
    ['citation', 'draft'],
    ['discarded', 'discarded'],
    ['cluster', 'cluster'],
    ['', 'draft'],
  ];
  for (const [cls, expected] of cases) {
    it(`classe "${cls}" → ${expected}`, () => {
      const li = document.createElement('li');
      li.className = ('row ' + cls).trim();
      expect(hooks.rowState(li)).toBe(expected);
    });
  }
});

describe('mode focus : enchaînement des décisions', () => {
  it('reco:deciding passe tout de suite à la prochaine reco à décider', () => {
    mountFocus([['r1', '', 'A'], ['r2', 'done', 'B'], ['r3', '', 'C']]);
    (window as any).__reco.setActiveRow(document.querySelector('[data-reco-id="r1"]'), { noScroll: true });
    fire('reco:deciding', { id: 'r1', action: 'validate' });
    expect(activeId()).toBe('r3');  // r2 déjà validée : sautée
    expect(document.querySelector('[data-fx-target="r1"]')!.getAttribute('data-state')).toBe('done');
    expect(document.querySelector('[data-fx-done]')!.textContent).toBe('2');
    expect(document.querySelector('[data-fx-target="r3"]')!.classList.contains('current')).toBe(true);
  });

  it('dernière décision → écran de fin, bilan au singulier', () => {
    mountFocus([['r1', 'done', 'A'], ['r2', '', 'B']]);
    fire('reco:deciding', { id: 'r2', action: 'discard' });
    const end = document.querySelector('[data-fx-end]') as HTMLElement;
    expect(end.hidden).toBe(false);
    expect(document.querySelector('[data-focus]')!.classList.contains('is-done')).toBe(true);
    expect(document.querySelector('[data-fx-count="done"]')!.textContent).toBe('1');
    expect(end.querySelector('[data-one]')!.textContent).toBe('validée');
  });

  it('« Revoir les recos » rouvre la première carte', () => {
    mountFocus([['r1', 'done', 'A']]);
    expect(hooks.updateEnd()).toBe(true);
    (document.querySelector('[data-fx-again]') as HTMLElement).click();
    expect(activeId()).toBe('r1');
    expect((document.querySelector('[data-fx-end]') as HTMLElement).hidden).toBe(true);
  });

  it('reco:failed revient sur la carte avec son état réel', () => {
    mountFocus([['r1', '', 'A'], ['r2', '', 'B']]);
    fire('reco:deciding', { id: 'r1', action: 'citation' });
    expect(activeId()).toBe('r2');
    fire('reco:failed', { id: 'r1' });
    expect(activeId()).toBe('r1');
    expect(document.querySelector('[data-fx-target="r1"]')!.getAttribute('data-state')).toBe('draft');
  });

  it('reco:replaced recopie titre, qui et état dans la liste', () => {
    mountFocus([['r1', '', 'A']]);
    const li = document.querySelector('[data-reco-id="r1"]') as HTMLElement;
    li.className = 'row done citation';
    li.querySelector('b')!.textContent = 'A corrigé';
    (li.querySelector('input[value="Carla"]') as HTMLInputElement).checked = true;
    fire('reco:replaced', { li });
    const item = document.querySelector('[data-fx-target="r1"]') as HTMLElement;
    expect(item.getAttribute('data-state')).toBe('citation');
    expect(item.querySelector('.fx-t')!.textContent).toBe('A corrigé');
    expect(item.querySelector('.fx-m')!.textContent).toBe('00:00:00 · Carla');
    expect(item.querySelector('.fx-sig')).toBeNull();  // traitée : plus d'alerte
  });

  it('nextPending tourne en boucle et renvoie null quand tout est décidé', () => {
    mountFocus([['r1', '', 'A'], ['r2', 'done', 'B']]);
    expect((hooks.nextPending('r2') as HTMLElement).dataset.recoId).toBe('r1');
    document.querySelector('[data-fx-target="r1"]')!.setAttribute('data-state', 'done');
    expect(hooks.nextPending('r2')).toBeNull();
  });

  it('un clic dans la liste active la carte ; le bouton téléphone ouvre la liste', () => {
    mountFocus([['r1', '', 'A'], ['r2', '', 'B']]);
    const toggle = document.querySelector('[data-fx-list-toggle]') as HTMLElement;
    toggle.click();
    expect(document.querySelector('[data-fx-list]')!.classList.contains('open')).toBe(true);
    (document.querySelector('[data-fx-target="r2"]') as HTMLElement).click();
    expect(activeId()).toBe('r2');
    expect(document.querySelector('[data-fx-list]')!.classList.contains('open')).toBe(false);
    expect(document.querySelector('[data-fx-pos]')!.textContent).toBe('2');
  });
});

describe('mode focus : retouches de l’audit', () => {
  it('reco:restored (« ↩ Annuler ») ramène sur la carte rétablie', () => {
    mountFocus([['r1', '', 'A'], ['r2', '', 'B']]);
    fire('reco:deciding', { id: 'r1', action: 'validate' });
    expect(activeId()).toBe('r2');
    fire('reco:restored', { id: 'r1' });
    expect(activeId()).toBe('r1');
    expect(document.querySelector('[data-fx-target="r1"]')!.getAttribute('data-state')).toBe('draft');
  });

  it('la barre de progression avance en scaleX', () => {
    mountFocus([['r1', '', 'A'], ['r2', '', 'B']]);
    fire('reco:deciding', { id: 'r1', action: 'discard' });
    expect((document.querySelector('[data-fx-bar]') as HTMLElement).style.transform).toBe('scaleX(0.50)');
  });

  it('changer de carte l’annonce et l’anime dans le bon sens', () => {
    mountFocus([['r1', '', 'A'], ['r2', '', 'B']]);
    document.body.insertAdjacentHTML('beforeend', '<div data-announce aria-live="polite"></div>');
    const setActive = (window as any).__reco.setActiveRow;
    setActive(document.querySelector('[data-reco-id="r1"]'), { noScroll: true });
    setActive(document.querySelector('[data-reco-id="r2"]'), { noScroll: true });
    expect(document.querySelector('[data-announce]')!.textContent).toBe('Reco 2 sur 2 : B');
    expect(document.querySelector('[data-reco-id="r2"]')!.classList.contains('fx-enter-next')).toBe(true);
    setActive(document.querySelector('[data-reco-id="r1"]'), { noScroll: true });
    expect(document.querySelector('[data-reco-id="r1"]')!.classList.contains('fx-enter-prev')).toBe(true);
  });

  it('le menu ⋯ se ferme au clic à côté et sur Échap', () => {
    mountFocus([['r1', '', 'A']]);
    const li = document.querySelector('[data-reco-id="r1"]') as HTMLElement;
    li.insertAdjacentHTML('afterbegin',
      '<details class="more" open><summary>⋯</summary><div class="more-panel"><a href="#x">Éditer</a></div></details>');
    const menu = li.querySelector('details.more') as HTMLDetailsElement;
    (menu.querySelector('a') as HTMLElement).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(menu.open).toBe(true);  // clic DANS le menu : il reste ouvert
    (li.querySelector('b') as HTMLElement).click();
    expect(menu.open).toBe(false);
    menu.open = true;
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(menu.open).toBe(false);
  });
});

describe('encadré « À vérifier »', () => {
  it('« Corriger » décoche le prénom et coche le nom complet', () => {
    mountFocus([['r1', '', 'A']]);
    const li = document.querySelector('[data-reco-id="r1"]') as HTMLElement;
    (li.querySelector('input[value="Carla"]') as HTMLInputElement).checked = true;
    li.insertAdjacentHTML('afterbegin',
      '<button type="button" class="verif-fix" data-fix-from="Carla" data-fix-to="Carla de Coignac">x</button>');
    (li.querySelector('.verif-fix') as HTMLButtonElement).click();
    expect((li.querySelector('input[value="Carla"]') as HTMLInputElement).checked).toBe(false);
    expect((li.querySelector('input[value="Carla de Coignac"]') as HTMLInputElement).checked).toBe(true);
    expect((li.querySelector('.verif-fix') as HTMLButtonElement).disabled).toBe(true);
  });

  it('un nom absent des cases va dans « autre nom »', () => {
    mountFocus([['r1', '', 'A']]);
    const li = document.querySelector('[data-reco-id="r1"]') as HTMLElement;
    li.insertAdjacentHTML('afterbegin',
      '<button type="button" class="verif-fix" data-fix-from="Kyan" data-fix-to="Kyan Khojandi">x</button>');
    (li.querySelector('.verif-fix') as HTMLButtonElement).click();
    expect((li.querySelector('input[name="other"]') as HTMLInputElement).value).toBe('Kyan Khojandi');
  });

  it('« Marquer Leur œuvre » soumet l’action guest-work', () => {
    mountFocus([['r1', '', 'A']]);
    const li = document.querySelector('[data-reco-id="r1"]') as HTMLElement;
    const form = li.querySelector('form') as HTMLFormElement;
    let submitter = '';
    form.requestSubmit = (b?: HTMLElement | null) => { submitter = (b as HTMLButtonElement).value; };
    li.insertAdjacentHTML('afterbegin',
      '<button type="button" class="verif-fix" data-fix-action="guest-work">x</button>');
    (li.querySelector('.verif-fix') as HTMLButtonElement).click();
    expect(submitter).toBe('guest-work');
  });
});

describe('accueil : filtre des épisodes', () => {
  it('filtre sans tenir compte des accents ni de la casse', () => {
    document.body.innerHTML =
      '<ul><li data-ep-row>Géraldine Nakache</li><li data-ep-row>Babor</li></ul>';
    hooks.filterEpisodes('geraldine');
    const rows = document.querySelectorAll('[data-ep-row]') as NodeListOf<HTMLElement>;
    expect(rows[0].hidden).toBe(false);
    expect(rows[1].hidden).toBe(true);
    hooks.filterEpisodes('');
    expect(rows[1].hidden).toBe(false);
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
