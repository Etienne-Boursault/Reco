(() => {
  // review_client_focus.js — relecture « focus » d'un épisode (/ep) : une
  // carte à la fois, la liste de l'épisode à côté, la progression, l'écran de
  // fin ; plus le filtre de l'accueil. Chargé APRÈS le core et le clavier :
  // consomme window.__reco.{initOnReady,setActiveRow,toast} et écoute les
  // événements qu'ils émettent :
  //   reco:active   — une carte devient active (clavier, clic, init) ;
  //   reco:replaced — une carte a été remplacée par sa version fraîche (AJAX) ;
  //   reco:deciding — une décision /save part → passer tout de suite à la suivante ;
  //   reco:decided  — le serveur l'a enregistrée ;
  //   reco:failed   — il l'a refusée (ou le réseau a lâché) → revenir sur la carte.
  if (window.__recoFocusInit) return;
  window.__recoFocusInit = true;
  const initOnReady = window.__reco.initOnReady;

  const PENDING = new Set(['draft', 'cluster']);

  function root() { return document.querySelector('[data-focus]'); }

  function rowId(li) {
    return li.getAttribute('data-reco-id') || li.getAttribute('data-cluster-id') || '';
  }

  function findRow(id) {
    const q = CSS.escape(id);
    return document.querySelector(
      '.ep > ul > li.row[data-reco-id="' + q + '"], .ep > ul > li.row[data-cluster-id="' + q + '"]'
    );
  }

  function items() { return Array.from(document.querySelectorAll('[data-fx-target]')); }

  function itemFor(id) {
    return document.querySelector('[data-fx-target="' + CSS.escape(id) + '"]');
  }

  // Même partition que review_render_focus.entry_state côté serveur.
  function rowState(li) {
    const c = li.classList;
    if (c.contains('cluster')) return 'cluster';
    if (c.contains('discarded')) return 'discarded';
    if (!c.contains('done')) return 'draft';
    if (c.contains('citation')) return 'citation';
    return c.contains('guestwork') ? 'guestwork' : 'done';
  }

  // Recopie dans la liste ce que la carte fraîche dit d'elle-même.
  function syncItem(li) {
    const item = itemFor(rowId(li));
    if (!item) return;
    const state = rowState(li);
    item.setAttribute('data-state', state);
    const title = li.querySelector('.hd > b');
    const t = item.querySelector('.fx-t');
    if (title && t) t.textContent = title.textContent;
    const who = Array.from(li.querySelectorAll('input[name="who"]:checked'))
      .map((i) => i.value).join(', ');
    const m = item.querySelector('.fx-m');
    if (m) {
      m.textContent = [item.getAttribute('data-time') || '', who]
        .filter(Boolean).join(' · ');
    }
    const sig = item.querySelector('.fx-sig');
    const n = parseInt(li.getAttribute('data-signals') || '0', 10);
    if (sig && (!n || !PENDING.has(state))) sig.remove();
  }

  function updateProgress() {
    const all = items();
    const done = all.filter((i) => !PENDING.has(i.getAttribute('data-state'))).length;
    const elDone = document.querySelector('[data-fx-done]');
    const bar = document.querySelector('[data-fx-bar]');
    if (elDone) elDone.textContent = String(done);
    // transform (et non width) : l'animation reste sur le compositeur.
    if (bar) bar.style.transform = 'scaleX(' + (all.length ? done / all.length : 1).toFixed(2) + ')';
  }

  // Bilan de l'écran de fin (validées, évoquées, etc.).
  function updateCounts() {
    const all = items();
    document.querySelectorAll('[data-fx-count]').forEach((b) => {
      const n = all.filter((i) => i.getAttribute('data-state') === b.getAttribute('data-fx-count')).length;
      b.textContent = String(n);
      const label = b.nextElementSibling;
      if (label && label.hasAttribute('data-one')) {
        label.textContent = label.getAttribute(n <= 1 ? 'data-one' : 'data-many');
      }
    });
  }

  // Écran de fin : révélé quand plus rien n'est à décider.
  function updateEnd() {
    const r = root();
    const end = document.querySelector('[data-fx-end]');
    if (!r || !end) return false;
    updateCounts();
    const all = items();
    const finished = all.length > 0 && !all.some((i) => PENDING.has(i.getAttribute('data-state')));
    end.hidden = !finished;
    r.classList.toggle('is-done', finished);
    return finished;
  }

  // Position de la carte affichée juste avant : donne le sens du changement.
  let lastPos = 0;

  // La carte entre du côté où l'on va : de la droite quand on avance, de la
  // gauche quand on revient. Rien au premier affichage.
  function animateEnter(li, pos) {
    if (!li || !lastPos || pos === lastPos) return;
    li.classList.remove('fx-enter-next', 'fx-enter-prev');
    void li.offsetWidth;  // relance l'animation si la classe était déjà là
    li.classList.add(pos > lastPos ? 'fx-enter-next' : 'fx-enter-prev');
    li.addEventListener('animationend', () => {
      li.classList.remove('fx-enter-next', 'fx-enter-prev');
    }, { once: true });
  }

  function announce(text) {
    const zone = document.querySelector('[data-announce]');
    if (zone) zone.textContent = text;
  }

  function markCurrent(li) {
    const id = li ? rowId(li) : '';
    let pos = 0;
    const all = items();
    all.forEach((item, i) => {
      const on = item.getAttribute('data-fx-target') === id;
      item.classList.toggle('current', on);
      if (on) {
        pos = i + 1;
        item.setAttribute('aria-current', 'true');
        if (item.scrollIntoView) item.scrollIntoView({ block: 'nearest' });
      } else {
        item.removeAttribute('aria-current');
      }
    });
    const elPos = document.querySelector('[data-fx-pos]');
    if (elPos && pos) elPos.textContent = String(pos);
    if (pos) {
      animateEnter(li, pos);
      const t = all[pos - 1].querySelector('.fx-t');
      if (lastPos) announce('Reco ' + pos + ' sur ' + all.length + ' : ' + (t ? t.textContent : ''));
      lastPos = pos;
    }
  }

  // Prochaine reco à décider après `id`, dans l'ordre de la liste (en boucle).
  function nextPending(id) {
    const all = items();
    const start = all.findIndex((i) => i.getAttribute('data-fx-target') === id);
    for (let k = 1; k <= all.length; k++) {
      const item = all[(start + k + all.length) % all.length];
      if (PENDING.has(item.getAttribute('data-state'))) {
        return findRow(item.getAttribute('data-fx-target'));
      }
    }
    return null;
  }

  function activate(li, opts) {
    if (li && window.__reco.setActiveRow) window.__reco.setActiveRow(li, opts);
  }

  function closeListOnPhone() {
    const nav = document.querySelector('[data-fx-list]');
    const toggle = document.querySelector('[data-fx-list-toggle]');
    if (nav) nav.classList.remove('open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }

  document.addEventListener('reco:active', (e) => {
    if (!root()) return;
    const r = root();
    // Choisir une carte, c'est vouloir la voir, même après « Tout est décidé ».
    if (r.classList.contains('is-done')) {
      r.classList.remove('is-done');
      const end = document.querySelector('[data-fx-end]');
      if (end) end.hidden = true;
    }
    markCurrent(e.detail && e.detail.li);
  });

  document.addEventListener('reco:replaced', (e) => {
    if (!root() || !e.detail || !e.detail.li) return;
    syncItem(e.detail.li);
    updateProgress();
  });

  // État attendu d'une décision, le temps que le serveur réponde (la carte
  // fraîche, via reco:replaced, fait ensuite foi).
  const PREDICTED = {
    validate: 'done', citation: 'citation', discard: 'discarded', 'guest-work': 'guestwork',
  };

  document.addEventListener('reco:deciding', (e) => {
    if (!root() || !e.detail) return;
    const item = itemFor(e.detail.id);
    const state = PREDICTED[e.detail.action];
    if (!item || !state) return;
    item.setAttribute('data-state', state);
    updateProgress();
    if (updateEnd()) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    activate(nextPending(e.detail.id));
  });

  document.addEventListener('reco:decided', () => {
    if (root()) updateCounts();
  });

  // Échec de l'enregistrement, ou décision annulée (« ↩ Annuler ») : retour
  // sur la carte, avec son vrai état.
  function backTo(e) {
    if (!root() || !e.detail) return;
    const li = findRow(e.detail.id);
    if (!li) return;
    syncItem(li);
    updateProgress();
    updateEnd();
    activate(li);
  }
  document.addEventListener('reco:failed', backTo);
  document.addEventListener('reco:restored', backTo);

  // Menu ⋯ : se ferme comme un menu (clic à côté, Échap), pas seulement en
  // recliquant sur ⋯.
  function closeMenus(except) {
    document.querySelectorAll('details.more[open]').forEach((d) => {
      if (d !== except) d.open = false;
    });
  }
  document.addEventListener('click', (e) => closeMenus(e.target.closest('details.more')), true);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && document.querySelector('details.more[open]')) {
      closeMenus(null);
      e.stopImmediatePropagation();  // Échap ferme le menu, pas l'édition en cours
    }
  }, true);

  document.addEventListener('click', (e) => {
    const target = e.target.closest('[data-fx-target]');
    if (target) {
      activate(findRow(target.getAttribute('data-fx-target')));
      closeListOnPhone();
      return;
    }
    const toggle = e.target.closest('[data-fx-list-toggle]');
    if (toggle) {
      const nav = toggle.closest('[data-fx-list]');
      const open = nav && nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      return;
    }
    if (e.target.closest('[data-fx-again]')) {
      const first = items()[0];
      activate(first && findRow(first.getAttribute('data-fx-target')));
      return;
    }
    const fix = e.target.closest('.verif-fix');
    if (fix) applyFix(fix);
  });

  // Correction proposée par l'encadré « À vérifier ».
  function applyFix(btn) {
    const li = btn.closest('li.row');
    const form = li && li.querySelector('form[action="/save"]');
    if (!form) return;
    const action = btn.getAttribute('data-fix-action');
    if (action) {
      const submit = form.querySelector('button[name="action"][value="' + CSS.escape(action) + '"]');
      if (submit && typeof form.requestSubmit === 'function') form.requestSubmit(submit);
      return;
    }
    const from = btn.getAttribute('data-fix-from') || '';
    const to = btn.getAttribute('data-fix-to') || '';
    form.querySelectorAll('input[name="who"]').forEach((i) => {
      if (i.value === from) i.checked = false;
      if (i.value === to) i.checked = true;
    });
    if (!form.querySelector('input[name="who"][value="' + CSS.escape(to) + '"]')) {
      const other = form.querySelector('input[name="other"]');
      if (other) other.value = to;
    }
    btn.disabled = true;
    btn.textContent = 'Corrigé · enregistré à la décision';
  }

  // --- Accueil : filtre des épisodes ---------------------------------------
  function fold(s) {
    return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  function filterEpisodes(q) {
    const needle = fold(q).trim();
    document.querySelectorAll('[data-ep-row]').forEach((row) => {
      row.hidden = !!needle && !fold(row.textContent).includes(needle);
    });
  }

  document.addEventListener('input', (e) => {
    const t = e.target;
    if (t instanceof HTMLInputElement && t.hasAttribute('data-ep-filter')) filterEpisodes(t.value);
  });

  function initFocus() {
    const r = root();
    if (!r) return;
    r.classList.add('fx-ready');
    // Au téléphone, le panneau des invités (ouvert par défaut) repousserait
    // la carte sous la moitié de l'écran : il se replie.
    const guests = r.querySelector('details.guests');
    if (guests && window.matchMedia && window.matchMedia('(max-width:760px)').matches) {
      guests.open = false;
    }
    markCurrent(document.querySelector('li.row.active'));
    updateProgress();
    updateEnd();
  }
  initOnReady(initFocus);

  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      rowState: rowState,
      nextPending: nextPending,
      updateEnd: updateEnd,
      filterEpisodes: filterEpisodes,
      initFocus: initFocus,
    });
  }
})();
