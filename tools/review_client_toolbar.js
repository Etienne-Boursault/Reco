(() => {
  // review_client_toolbar.js — barre d'outils épisode : tri des cartes + repli
  // des recos traitées. Découpé de review_client.js (M4 CR cumulative).
  // Chargé APRÈS le core : consomme window.__reco.initOnReady.
  if (window.__recoToolbarInit) return;
  window.__recoToolbarInit = true;
  const initOnReady = window.__reco.initOnReady;

  // --- REVIEW TOOLBAR : tri (#2) + repli des traités (#1) ------------------
  // Barre injectée en tête de la liste des recos d'un épisode. Deux contrôles :
  //  - un <select> de tri qui réordonne les <li.row> côté client ;
  //  - un bouton qui replie les cartes déjà traitées (validées / citations /
  //    écartées) en une ligne compacte (clic sur une carte repliée = déplier).
  // État persisté en localStorage (survit aux reloads PRG après V/C/D).

  // Normalise un texte pour tri/compare : sans accents, minuscules, trim.
  function normText(s) {
    return (s || '')
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase().trim();
  }

  // Les <li> triables : toutes les .row sauf la ligne « + Ajouter une reco »
  // (épinglée en fin de liste).
  function getSortableItems(ul) {
    return Array.from(ul.children).filter(
      (li) => li.classList && li.classList.contains('row')
        && !li.classList.contains('add-reco-row')
    );
  }

  function rowStatus(li) {
    if (li.classList.contains('cluster')) return 'cluster';
    if (li.classList.contains('discarded')) return 'discarded';
    if (li.classList.contains('citation')) return 'citation';
    if (li.classList.contains('done')) return 'done';
    return 'draft';
  }

  function rowTitle(li) {
    const b = li.querySelector('b');
    return normText(b ? b.textContent : '');
  }

  function rowTypeLabel(li) {
    const t = li.querySelector('.type-emoji');
    return normText(t ? (t.getAttribute('title') || t.textContent) : '');
  }

  // Rangs de statut pour les tris « à traiter » / « traités ». Les clusters
  // (décision de fusion en attente) comptent comme « à traiter ».
  // N3 — `guestwork` est ajouté défensivement : aujourd'hui `rowStatus` renvoie
  // 'done' pour une œuvre d'invité validée (classe .done), mais si un futur
  // changement le faisait renvoyer 'guestwork', un rang undefined casserait le
  // tri (NaN). On le range comme un item traité (comme done/citation).
  const TODO_RANK = { draft: 0, cluster: 0, citation: 1, done: 1, guestwork: 1, discarded: 2 };
  const DONE_RANK = { done: 0, citation: 0, guestwork: 0, discarded: 1, draft: 2, cluster: 2 };

  function getEpisodeList() {
    const ep = document.querySelector('section.ep');
    if (!ep) return null;
    return ep.querySelector('ul');
  }

  // Fige l'ordre chronologique initial (rendu serveur) une seule fois.
  function captureOriginalOrder(ul) {
    getSortableItems(ul).forEach((li, i) => {
      if (li.dataset.origIdx === undefined) li.dataset.origIdx = String(i);
    });
  }

  function applySort(mode) {
    const ul = getEpisodeList();
    if (!ul) return;
    captureOriginalOrder(ul);
    const items = getSortableItems(ul);
    const oi = (li) => parseInt(li.dataset.origIdx || '0', 10);
    let cmp;
    switch (mode) {
      case 'alpha':
        cmp = (a, b) => rowTitle(a).localeCompare(rowTitle(b)) || oi(a) - oi(b);
        break;
      case 'todo':
        cmp = (a, b) => (TODO_RANK[rowStatus(a)] - TODO_RANK[rowStatus(b)])
          || oi(a) - oi(b);
        break;
      case 'done':
        cmp = (a, b) => (DONE_RANK[rowStatus(a)] - DONE_RANK[rowStatus(b)])
          || oi(a) - oi(b);
        break;
      case 'type':
        cmp = (a, b) => rowTypeLabel(a).localeCompare(rowTypeLabel(b))
          || oi(a) - oi(b);
        break;
      default: // 'chrono'
        cmp = (a, b) => oi(a) - oi(b);
    }
    items.sort(cmp);
    const addRow = ul.querySelector('.add-reco-row');
    items.forEach((li) => ul.appendChild(li));
    if (addRow) ul.appendChild(addRow); // toujours en dernier
  }

  function countProcessed() {
    return document.querySelectorAll(
      '.row.done, .row.discarded, .row.citation'
    ).length;
  }

  function updateCollapseLabel(btn) {
    const on = document.body.classList.contains('collapse-done');
    const n = countProcessed();
    btn.textContent = (on ? '🗂 Déplier les traités' : '🗂 Replier les traités')
      + (n ? ` (${n})` : '');
  }

  function setCollapse(on, btn) {
    document.body.classList.toggle('collapse-done', !!on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    try { localStorage.setItem('reco-collapse-done', on ? '1' : '0'); } catch (_) {}
    updateCollapseLabel(btn);
  }

  // Clic sur une carte repliée → déplier juste celle-ci (toggle .force-expand).
  // On ignore les clics sur les éléments interactifs (boutons, liens, champs).
  function setupCollapseExpandClicks() {
    document.addEventListener('click', (e) => {
      if (!document.body.classList.contains('collapse-done')) return;
      const li = e.target.closest(
        'li.row.done, li.row.discarded, li.row.citation'
      );
      if (!li) return;
      if (e.target.closest('a, button, input, select, textarea, label, form')) {
        return;
      }
      li.classList.toggle('force-expand');
    });
  }
  initOnReady(setupCollapseExpandClicks);

  const SORT_OPTIONS = [
    ['chrono', 'Chronologique'],
    ['alpha', 'Alphabétique (A→Z)'],
    ['todo', 'À traiter d’abord'],
    ['done', 'Traités d’abord'],
    ['type', 'Par type'],
  ];

  function buildToolbar() {
    const bar = document.createElement('div');
    bar.className = 'review-toolbar';

    const sortLabel = document.createElement('label');
    sortLabel.className = 'rt-sort';
    sortLabel.appendChild(document.createTextNode('Trier : '));
    const sel = document.createElement('select');
    sel.setAttribute('data-sort-select', '1');
    SORT_OPTIONS.forEach(([v, l]) => {
      const o = document.createElement('option');
      o.value = v;
      o.textContent = l;
      sel.appendChild(o);
    });
    sortLabel.appendChild(sel);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('data-collapse-toggle', '1');

    bar.appendChild(sortLabel);
    bar.appendChild(btn);
    return { bar, sel, btn };
  }

  function setupReviewToolbar() {
    const ul = getEpisodeList();
    if (!ul) return;
    captureOriginalOrder(ul);
    if (document.querySelector('.review-toolbar')) return;
    const ep = ul.closest('section.ep');
    if (!ep) return;

    const { bar, sel, btn } = buildToolbar();
    ep.insertBefore(bar, ul);

    // Tri : restaure l'état persisté puis applique.
    let storedSort = 'chrono';
    try { storedSort = localStorage.getItem('reco-sort') || 'chrono'; } catch (_) {}
    if (!SORT_OPTIONS.some(([v]) => v === storedSort)) storedSort = 'chrono';
    sel.value = storedSort;
    applySort(storedSort);
    sel.addEventListener('change', () => {
      applySort(sel.value);
      try { localStorage.setItem('reco-sort', sel.value); } catch (_) {}
    });

    // Repli : restaure l'état persisté.
    let storedCollapse = '0';
    try { storedCollapse = localStorage.getItem('reco-collapse-done') || '0'; } catch (_) {}
    setCollapse(storedCollapse === '1', btn);
    btn.addEventListener('click', () => {
      setCollapse(!document.body.classList.contains('collapse-done'), btn);
    });
  }
  initOnReady(setupReviewToolbar);


  // Hooks de test (jamais définis en prod — cf. tests/js/).
  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      normText: normText,
      rowStatus: rowStatus,
      rowTitle: rowTitle,
      applySort: applySort,
      getSortableItems: getSortableItems,
      TODO_RANK: TODO_RANK,
      DONE_RANK: DONE_RANK,
    });
  }
})();
