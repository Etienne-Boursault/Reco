(() => {
  // review_client_table.js — tableau de pilotage (/tableau).
  //
  // Deux responsabilités :
  //  - TRI côté client sur n'importe quelle colonne (clic sur l'en-tête, un
  //    second clic inverse le sens). ~1200 lignes = du DOM raisonnable, et un
  //    tri sans rechargement ne fait pas perdre le commentaire en cours de
  //    frappe. Les clés sont pré-calculées côté serveur en `data-k-*`.
  //  - ENREGISTREMENT AU FIL DE L'EAU du commentaire (frappe débattue + flush
  //    au blur) et de la coche (au change). Pas de bouton « Tout enregistrer »
  //    qu'on oublierait de cliquer.
  //
  // Chargé APRÈS le core : consomme window.__reco.{initOnReady,toast}.
  if (window.__recoTableInit) return;
  window.__recoTableInit = true;
  const ns = window.__reco || {};
  const initOnReady = ns.initOnReady || ((fn) => fn());
  const toast = ns.toast || (() => {});

  const SORT_KEY_STORAGE = 'reco-table-sort';
  const DEBOUNCE_MS = 700;

  function getTable() {
    return document.getElementById('reco-table');
  }

  function getRows() {
    const table = getTable();
    if (!table) return [];
    return Array.from(table.querySelectorAll('tbody tr.tbl-row'));
  }

  // Fige l'ordre initial (rendu serveur = chronologique) pour servir de
  // départage stable : deux titres identiques restent dans l'ordre de départ.
  function captureOriginalOrder(rows) {
    rows.forEach((tr, i) => {
      if (tr.dataset.origIdx === undefined) tr.dataset.origIdx = String(i);
    });
  }

  function keyOf(tr, key) {
    return tr.getAttribute('data-k-' + key) || '';
  }

  function markHeaders(key, dir) {
    const table = getTable();
    if (!table) return;
    table.querySelectorAll('th[data-sort-key]').forEach((th) => {
      const on = th.getAttribute('data-sort-key') === key;
      th.setAttribute('aria-sort', on
        ? (dir === 'desc' ? 'descending' : 'ascending')
        : 'none');
      th.classList.toggle('tbl-sorted', on);
      th.classList.toggle('tbl-sorted-desc', on && dir === 'desc');
    });
  }

  function applySort(key, dir, numeric) {
    const table = getTable();
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = getRows();
    captureOriginalOrder(rows);
    const oi = (tr) => parseInt(tr.dataset.origIdx || '0', 10);
    const sign = dir === 'desc' ? -1 : 1;
    rows.sort((a, b) => {
      const va = keyOf(a, key);
      const vb = keyOf(b, key);
      let c;
      if (numeric) {
        c = (parseFloat(va) || 0) - (parseFloat(vb) || 0);
      } else if (va === vb) {
        c = 0;
      } else if (!va || !vb) {
        // Cellules vides TOUJOURS en bas — dans les deux sens de tri : une
        // colonne triée pour trouver ce qui manque n'a pas à commencer par
        // 300 lignes vides.
        return va ? -1 : 1;
      } else {
        c = va.localeCompare(vb);
      }
      return c ? c * sign : oi(a) - oi(b);
    });
    const frag = document.createDocumentFragment();
    rows.forEach((tr) => frag.appendChild(tr));
    tbody.appendChild(frag);
    markHeaders(key, dir);
  }

  function readStoredSort() {
    try {
      const raw = localStorage.getItem(SORT_KEY_STORAGE);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !parsed.key) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function storeSort(state) {
    try {
      localStorage.setItem(SORT_KEY_STORAGE, JSON.stringify(state));
    } catch (_) { /* mode privé : le tri marche, il n'est juste pas mémorisé */ }
  }

  function headerFor(key) {
    const table = getTable();
    if (!table) return null;
    return table.querySelector('th[data-sort-key="' + key + '"]');
  }

  function isNumeric(th) {
    return !!th && th.getAttribute('data-sort-numeric') === '1';
  }

  function sortByHeader(th) {
    const key = th.getAttribute('data-sort-key');
    const current = readStoredSort();
    const dir = (current && current.key === key && current.dir === 'asc')
      ? 'desc' : 'asc';
    applySort(key, dir, isNumeric(th));
    storeSort({ key: key, dir: dir });
  }

  function restoreSort() {
    const state = readStoredSort();
    if (!state) return;
    const th = headerFor(state.key);
    if (!th) return;
    applySort(state.key, state.dir, isNumeric(th));
  }
  initOnReady(restoreSort);

  // --- Enregistrement au fil de l'eau --------------------------------------
  function rowOf(el) {
    return el.closest('tr.tbl-row');
  }

  function flagSaved(el, ok) {
    const cell = el.closest('td') || el;
    cell.classList.toggle('tbl-saved', ok);
    cell.classList.toggle('tbl-save-error', !ok);
  }

  async function postForm(url, fields) {
    const body = new URLSearchParams();
    Object.keys(fields).forEach((k) => body.set(k, fields[k]));
    const r = await fetch(url, {
      method: 'POST',
      headers: { Accept: 'application/json' },
      body: body,
    });
    return r.json();
  }

  // Normalise comme `common.normalize_text` côté serveur : sans accent,
  // minuscules, trim. Garde la clé de tri cohérente après une édition locale.
  function normKey(s) {
    return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().trim();
  }

  async function saveCuration(el, fields) {
    const tr = rowOf(el);
    if (!tr) return null;
    let data;
    try {
      data = await postForm('/curation', Object.assign({ id: tr.dataset.id }, fields));
    } catch (_) {
      flagSaved(el, false);
      toast('Enregistrement impossible (serveur injoignable).', 'error');
      return null;
    }
    if (!data || data.kind === 'error') {
      flagSaved(el, false);
      toast((data && data.message) || 'Enregistrement refusé.', 'error');
      return data;
    }
    // Les clés de tri suivent l'édition : re-trier juste après ne renvoie pas
    // la ligne à sa place d'avant.
    tr.setAttribute('data-k-comment', normKey(data.comment));
    tr.setAttribute('data-k-check', data.checked ? '1' : '0');
    flagSaved(el, true);
    return data;
  }

  function saveComment(textarea) {
    return saveCuration(textarea, { comment: textarea.value });
  }

  function saveCheck(box) {
    return saveCuration(box, { checked: box.checked ? '1' : '0' });
  }

  async function acceptType(box) {
    const tr = rowOf(box);
    if (!tr) return null;
    let data;
    try {
      data = await postForm('/accept-type', { id: tr.dataset.id });
    } catch (_) {
      box.checked = false;
      toast('Reclassement impossible (serveur injoignable).', 'error');
      return null;
    }
    if (!data || data.kind === 'error') {
      box.checked = false;
      toast((data && data.message) || 'Reclassement refusé.', 'error');
      return data;
    }
    const cell = tr.querySelector('.tbl-c-types');
    if (cell) cell.textContent = data.labels;
    tr.setAttribute('data-k-types', normKey(data.labels));
    toast(data.message, 'success');
    return data;
  }

  // Débat par élément : on n'écrit pas à chaque frappe, mais on n'attend pas
  // non plus un clic sur « Enregistrer » (qu'on oublierait).
  const timers = new Map();

  function scheduleSave(textarea) {
    clearTimeout(timers.get(textarea));
    timers.set(textarea, setTimeout(() => {
      timers.delete(textarea);
      saveComment(textarea);
    }, DEBOUNCE_MS));
  }

  function flushSave(textarea) {
    if (!timers.has(textarea)) return false;
    clearTimeout(timers.get(textarea));
    timers.delete(textarea);
    saveComment(textarea);
    return true;
  }

  // Filet : quitter l'onglet (changement d'onglet, fermeture) sans avoir quitté
  // le champ perdrait les dernières frappes encore en attente de débat. On
  // vide la file dès que la page passe en arrière-plan.
  function flushAll() {
    Array.from(timers.keys()).forEach(flushSave);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushAll();
  });

  // Listeners DÉLÉGUÉS sur document : posés une fois, ils survivent à un
  // re-tri (qui déplace les <tr>) sans qu'on ait à les réattacher.
  document.addEventListener('input', (e) => {
    const ta = e.target.closest && e.target.closest('textarea.tbl-comment');
    if (ta) scheduleSave(ta);
  });
  document.addEventListener('focusout', (e) => {
    const ta = e.target.closest && e.target.closest('textarea.tbl-comment');
    if (ta) flushSave(ta);
  });
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (!el.closest) return;
    if (el.closest('input.tbl-check')) saveCheck(el);
    else if (el.closest('input.tbl-accept')) acceptType(el);
  });
  document.addEventListener('click', (e) => {
    const th = e.target.closest && e.target.closest('th[data-sort-key]');
    if (th) sortByHeader(th);
  });

  // Hooks de test (jamais définis en prod — cf. tests/js/).
  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      tableApplySort: applySort,
      tableRowIds: () => getRows().map((tr) => tr.dataset.id),
      tableSortByHeader: sortByHeader,
      tableRestoreSort: restoreSort,
      tableSaveComment: saveComment,
      tableSaveCheck: saveCheck,
      tableAcceptType: acceptType,
      tableScheduleSave: scheduleSave,
      tableFlushSave: flushSave,
      tableFlushAll: flushAll,
      tableNormKey: normKey,
    });
  }
})();
