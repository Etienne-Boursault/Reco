(() => {
  // review_client_resize.js — largeur des colonnes ajustable sur /tableau.
  //
  // POURQUOI UN MODULE À PART : les fichiers client du dépôt tiennent sous
  // 500 lignes et se concatènent dans l'ordre déclaré par
  // `review_render_common._CLIENT_JS_FILES`. Le tri et l'autosave vivent dans
  // `review_client_table.js` ; ceci n'y touche pas.
  //
  // TROIS PIÈGES, et ce qu'on en fait :
  //
  // 1. Le `<th>` EST un bouton de tri. Un glisser-déposer qui remonterait
  //    jusqu'à lui trierait la colonne à chaque relâchement. La poignée est
  //    donc un frère du bouton (pas un enfant), on arrête la propagation dès
  //    le `pointerdown`, et le premier `click` qui suit un vrai déplacement
  //    est avalé en phase de CAPTURE — sans quoi le navigateur le livre au
  //    bouton même si la souris a bougé de 200 px.
  //
  // 2. `table-layout` est en `auto` : une largeur posée sur un `<th>` n'y est
  //    qu'une SUGGESTION, le navigateur reste libre de l'ignorer pour faire
  //    tenir le contenu. On ne bascule en `fixed` qu'au premier ajustement, et
  //    en figeant d'abord les largeurs mesurées de TOUTES les colonnes : sans
  //    ça, la table se réorganiserait d'un coup au premier pixel glissé. Tant
  //    que l'utilisateur ne redimensionne rien, l'ajustement automatique reste
  //    en place — c'est lui qui donne le meilleur résultat par défaut.
  //
  // 3. En `table-layout: fixed`, seules les cellules de la PREMIÈRE rangée
  //    dictent les largeurs. Poser la largeur sur les `<th>` suffit donc, et
  //    les 1200 `<td>` n'ont pas à être touchés — ce qui rend le glissement
  //    fluide au lieu de repeindre 9600 cellules à chaque pixel.
  //
  // Chargé APRÈS le core : consomme window.__reco.initOnReady.
  if (window.__recoResizeInit) return;
  window.__recoResizeInit = true;
  const ns = window.__reco || {};
  const initOnReady = ns.initOnReady || ((fn) => fn());

  const STORAGE = 'reco-table-widths';
  const MIN_W = 40;      // px — en deçà, l'en-tête n'est plus lisible
  const MAX_W = 1200;    // px — garde-fou contre un glissement parti trop loin
  const STEP = 16;       // px — pas des flèches du clavier
  const DRAG_SLOP = 3;   // px — en deçà, c'est un clic, pas un glissement

  function getTable() {
    return document.getElementById('reco-table');
  }

  function headers(table) {
    return Array.from(table.querySelectorAll('thead th[data-sort-key]'));
  }

  // --- Persistance --------------------------------------------------------
  // { cleColonne: largeurPx }. Le mode privé fait échouer localStorage : le
  // redimensionnement marche quand même, il n'est simplement pas mémorisé.
  function readStored() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE) || '{}');
      return (parsed && typeof parsed === 'object') ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function store(widths) {
    try {
      localStorage.setItem(STORAGE, JSON.stringify(widths));
    } catch (_) { /* pas de mémorisation, pas de casse */ }
  }

  function clamp(px) {
    return Math.max(MIN_W, Math.min(MAX_W, Math.round(px)));
  }

  // --- Passage en largeurs explicites -------------------------------------
  /**
   * Fige les largeurs ACTUELLEMENT calculées sur toutes les colonnes, puis
   * bascule la table en `table-layout: fixed`.
   *
   * Idempotent : une fois figée, la table le reste — refiger à chaque
   * glissement écraserait les largeurs déjà choisies par l'utilisateur.
   */
  function freeze(table) {
    if (table.dataset.widthsFrozen === '1') return;
    // Mesurer AVANT de changer quoi que ce soit : dès que `fixed` est posé,
    // les largeurs calculées changent et la mesure ne vaut plus rien.
    const mesures = headers(table).map((th) => th.getBoundingClientRect().width);
    headers(table).forEach((th, i) => {
      th.style.width = clamp(mesures[i]) + 'px';
    });
    table.style.tableLayout = 'fixed';
    table.dataset.widthsFrozen = '1';
  }

  function applyWidth(table, th, px) {
    freeze(table);
    const w = clamp(px);
    th.style.width = w + 'px';
    const widths = readStored();
    widths[th.dataset.sortKey] = w;
    store(widths);
    return w;
  }

  /** Restaure les largeurs mémorisées. Rien de mémorisé → rien à faire, et
   *  la table garde son ajustement automatique. */
  function restore(table) {
    const widths = readStored();
    const keys = Object.keys(widths);
    if (!keys.length) return;
    freeze(table);
    headers(table).forEach((th) => {
      const w = widths[th.dataset.sortKey];
      if (typeof w === 'number' && isFinite(w)) th.style.width = clamp(w) + 'px';
    });
  }

  /** Rend une colonne à sa largeur automatique (double-clic sur la poignée). */
  function reset(table, th) {
    const widths = readStored();
    delete widths[th.dataset.sortKey];
    store(widths);
    if (!Object.keys(widths).length) {
      // Plus aucune largeur retenue : on rend la main à l'ajustement
      // automatique plutôt que de laisser une table figée sur des mesures
      // qui ne veulent plus rien dire.
      headers(table).forEach((h) => { h.style.width = ''; });
      table.style.tableLayout = '';
      delete table.dataset.widthsFrozen;
      return;
    }
    // D'autres colonnes restent réglées : la table doit rester en `fixed`,
    // sinon elles sauteraient toutes. On donne à celle-ci une largeur issue
    // de son contenu d'en-tête plutôt que de la laisser à 0.
    th.style.width = '';
    const naturelle = th.getBoundingClientRect().width;
    th.style.width = clamp(naturelle || MIN_W * 3) + 'px';
  }

  // --- Glissement ---------------------------------------------------------
  function startDrag(table, th, handle, ev) {
    const departX = ev.clientX;
    const departW = th.getBoundingClientRect().width;
    let bouge = false;

    // `setPointerCapture` : le pointeur reste rattaché à la poignée même si le
    // curseur sort du tableau. Sans lui, un glissement rapide « décroche ».
    try { handle.setPointerCapture(ev.pointerId); } catch (_) { /* vieux navigateur */ }
    handle.classList.add('tbl-resizing');
    document.body.classList.add('tbl-resizing-body');

    const onMove = (e) => {
      const delta = e.clientX - departX;
      if (!bouge && Math.abs(delta) < DRAG_SLOP) return;
      bouge = true;
      applyWidth(table, th, departW + delta);
    };

    const onUp = () => {
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
      handle.classList.remove('tbl-resizing');
      document.body.classList.remove('tbl-resizing-body');
      // Avaler le `click` que le navigateur va livrer au bouton de tri.
      // En CAPTURE et une seule fois : si le geste n'a finalement produit
      // aucun clic, le écouteur se retire au tour de boucle suivant.
      if (bouge) {
        const avale = (e) => { e.stopPropagation(); e.preventDefault(); };
        document.addEventListener('click', avale, { capture: true, once: true });
        setTimeout(() => {
          document.removeEventListener('click', avale, { capture: true });
        }, 0);
      }
    };

    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  }

  // --- Montage ------------------------------------------------------------
  function mount() {
    const table = getTable();
    if (!table) return;             // page sans tableau : rien à faire
    restore(table);

    table.addEventListener('pointerdown', (ev) => {
      const handle = ev.target.closest('.tbl-resize');
      if (!handle || ev.button !== 0) return;
      const th = handle.closest('th');
      if (!th) return;
      // Le bouton de tri ne doit RIEN voir de ce geste.
      ev.preventDefault();
      ev.stopPropagation();
      startDrag(table, th, handle, ev);
    });

    table.addEventListener('dblclick', (ev) => {
      const handle = ev.target.closest('.tbl-resize');
      if (!handle) return;
      ev.preventDefault();
      ev.stopPropagation();
      const th = handle.closest('th');
      if (th) reset(table, th);
    });

    // Clavier : la page entière se pilote sans souris, la largeur aussi.
    table.addEventListener('keydown', (ev) => {
      const handle = ev.target.closest && ev.target.closest('.tbl-resize');
      if (!handle) return;
      const th = handle.closest('th');
      if (!th) return;
      if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
        ev.preventDefault();
        const delta = ev.key === 'ArrowRight' ? STEP : -STEP;
        applyWidth(table, th, th.getBoundingClientRect().width + delta);
      } else if (ev.key === 'Home' || ev.key === 'Escape') {
        ev.preventDefault();
        reset(table, th);
      }
    });
  }

  initOnReady(mount);

  // Exposé pour les tests (mêmes conventions que les autres modules client).
  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      resizeMount: mount,
      resizeClamp: clamp,
      resizeReadStored: readStored,
      resizeStore: store,
      resizeReset: reset,
      resizeFreeze: freeze,
      resizeApplyWidth: applyWidth,
      resizeRestore: restore,
      RESIZE_MIN_W: MIN_W,
      RESIZE_MAX_W: MAX_W,
      RESIZE_STEP: STEP,
    });
  }
})();
