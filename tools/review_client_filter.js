(() => {
  // review_client_filter.js — filtre par épisode sur /tableau.
  //
  // Le tri (review_client_table.js) RÉORDONNE les lignes ; ce module se
  // contente de les MASQUER. Les deux se composent donc sans se connaître :
  // trier ne révèle pas une ligne filtrée, filtrer ne perturbe pas l'ordre.
  // C'est aussi pourquoi le masquage passe par un attribut `hidden` sur le
  // `<tr>` plutôt que par un retrait du DOM — une ligne retirée perdrait son
  // commentaire en cours de frappe et son rang de tri.
  //
  // Chargé APRÈS le core : consomme window.__reco.initOnReady.
  if (window.__recoFilterInit) return;
  window.__recoFilterInit = true;
  const ns = window.__reco || {};
  const initOnReady = ns.initOnReady || ((fn) => fn());

  const STORAGE = 'reco-table-filter-ep';

  const el = (id) => document.getElementById(id);
  const getRows = () => Array.from(
    document.querySelectorAll('#reco-table tbody tr.tbl-row'));

  function readStored() {
    try {
      return localStorage.getItem(STORAGE) || '';
    } catch (_) {
      return '';
    }
  }

  function store(guid) {
    try {
      if (guid) localStorage.setItem(STORAGE, guid);
      else localStorage.removeItem(STORAGE);
    } catch (_) { /* mode privé : le filtre marche, il n'est pas mémorisé */ }
  }

  /**
   * Applique le filtre. `guid` vide = tout afficher.
   * Renvoie le nombre de lignes visibles — c'est ce que le compteur affiche,
   * et ce que les tests vérifient.
   */
  function apply(guid) {
    const rows = getRows();
    let visibles = 0;
    for (const tr of rows) {
      const ok = !guid || tr.dataset.ep === guid;
      // `hidden` plutôt que `style.display` : l'attribut est sémantique (les
      // lecteurs d'écran sautent la ligne) et se retire sans laisser de style
      // en ligne derrière lui.
      tr.hidden = !ok;
      if (ok) visibles += 1;
    }
    const compteur = el('tbl-filter-count');
    if (compteur) {
      compteur.textContent = guid
        ? `${visibles} reco${visibles > 1 ? 's' : ''} sur ${rows.length}`
        : '';
    }
    const clear = el('tbl-filter-clear');
    if (clear) clear.hidden = !guid;
    return visibles;
  }

  function mount() {
    const select = el('tbl-filter-ep');
    if (!select) return;             // page sans tableau : rien à faire

    // Restaurer le choix précédent — mais seulement s'il existe encore dans la
    // liste : un épisode peut avoir disparu (reco écartée, source changée), et
    // un filtre pointant dans le vide masquerait TOUT sans rien expliquer.
    const memorise = readStored();
    const connu = memorise &&
      Array.from(select.options).some((o) => o.value === memorise);
    if (connu) select.value = memorise;
    else if (memorise) store('');
    apply(connu ? memorise : '');

    select.addEventListener('change', () => {
      store(select.value);
      apply(select.value);
    });

    const clear = el('tbl-filter-clear');
    if (clear) {
      clear.addEventListener('click', () => {
        select.value = '';
        store('');
        apply('');
        select.focus();
      });
    }
  }

  initOnReady(mount);

  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      filterMount: mount,
      filterApply: apply,
      filterReadStored: readStored,
      filterStore: store,
    });
  }
})();
