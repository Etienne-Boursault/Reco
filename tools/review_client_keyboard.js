(() => {
  // review_client_keyboard.js — navigation clavier, carte active, lecteur YT,
  // recherche locale, overlay d'aide, auto-play. Découpé de review_client.js
  // (M4 CR cumulative — limite 500 lignes). Chargé APRÈS le core : consomme
  // window.__reco.{initOnReady,toast} et Y PUBLIE setActiveRow (utilisé par
  // l'AJAX du core pour ré-activer la carte après édition).
  if (window.__recoKeyboardInit) return;
  window.__recoKeyboardInit = true;
  const initOnReady = window.__reco.initOnReady;
  const toast = window.__reco.toast;

  // --- KEYBOARD NAVIGATION + ACTIVE CARD + YT API ---
  // Pack raccourcis clavier pour traiter les recos sans souris.
  // - Une carte « active » à la fois (`.row.active`), persistée par épisode
  //   en sessionStorage (clé `reco-active-{guid}`).
  // - J/K (ou ↓/↑) navigue ; V/C/D actionne ; E édite ; R ré-enrichit ;
  //   Espace play/pause YT ; T recharge YT au timecode ; [/] prev/next épisode ;
  //   / recherche locale ; ? overlay aide ; Esc ferme overlay/recherche.
  // - Auto-play optionnel (toggle 🔁 en haut, localStorage `reco-autoplay`).
  //
  // Compromis acceptés (cf. brief) :
  // - /save n'est pas AJAX-able aujourd'hui : V/C/D submit le form et
  //   provoquent un reload (la page se rafraîchit, OK pour cette itération).
  // - YouTube IFrame API : sur l'iframe `name="ytplayer"`, on ajoute `id` au
  //   boot et on instancie `YT.Player` une fois l'API JS chargée.

  const KB_ACTIVE_SKIP_DISCARDED = true;

  function getGuidFromUrl() {
    const m = window.location.search.match(/[?&]guid=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  // L4 — clé de persistance de la carte active. Sur une page épisode on la
  // scope au guid ; sur les pages sans guid (/doutes) on se rabat sur le
  // pathname pour NE PAS écrire une clé vide 'reco-active-' partagée entre
  // pages, tout en gardant la navigation clavier fonctionnelle.
  function activeStorageKey() {
    const guid = getGuidFromUrl();
    return 'reco-active-' + (guid || window.location.pathname);
  }

  function getRows(includeDiscarded) {
    const all = Array.from(document.querySelectorAll('li.row[data-reco-id]'));
    const filtered = all.filter((li) => !li.classList.contains('hidden-by-search'));
    if (includeDiscarded) return filtered;
    return filtered.filter((li) => !li.classList.contains('discarded'));
  }

  function getActiveRow() {
    return document.querySelector('li.row.active[data-reco-id]');
  }

  function setActiveRow(li, opts) {
    if (!li) return;
    document.querySelectorAll('li.row.active').forEach((n) => n.classList.remove('active'));
    li.classList.add('active');
    // L4 — clé scindée par guid (ou pathname en repli) : jamais de clé vide.
    try { sessionStorage.setItem(activeStorageKey(), li.getAttribute('data-reco-id') || ''); } catch (_) {}
    if (!opts || !opts.noScroll) {
      li.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    if (window.__recoAutoplayEnabled && (!opts || !opts.noAutoplay)) {
      scheduleAutoplay(li);
    }
  }

  function moveActive(direction, includeDiscarded) {
    const rows = getRows(includeDiscarded);
    if (rows.length === 0) return;
    const current = getActiveRow();
    let idx = current ? rows.indexOf(current) : -1;
    if (idx === -1) {
      idx = direction > 0 ? 0 : rows.length - 1;
    } else {
      idx = Math.max(0, Math.min(rows.length - 1, idx + direction));
    }
    setActiveRow(rows[idx]);
  }

  function initActiveRow() {
    // L4 — lecture via la même clé scindée (guid ou pathname) que l'écriture.
    let stored = '';
    try { stored = sessionStorage.getItem(activeStorageKey()) || ''; } catch (_) {}
    let target = null;
    if (stored) {
      target = document.querySelector(
        'li.row[data-reco-id="' + CSS.escape(stored) + '"]'
      );
    }
    if (!target) {
      const rows = getRows(false);
      target = rows[0] || null;
    }
    if (target) setActiveRow(target, { noScroll: true, noAutoplay: true });
  }
  initOnReady(initActiveRow);

  // --- YouTube IFrame API ---
  let __ytPlayer = null;
  let __ytReadyResolve = null;
  const __ytReady = new Promise((resolve) => { __ytReadyResolve = resolve; });

  function ensureYTApi() {
    if (document.querySelector('script[data-yt-api]')) return;
    const s = document.createElement('script');
    s.src = 'https://www.youtube.com/iframe_api';
    s.setAttribute('data-yt-api', '1');
    document.head.appendChild(s);
  }

  window.onYouTubeIframeAPIReady = function () {
    tryInstantiateYTPlayer();
  };

  function tryInstantiateYTPlayer() {
    const wrap = document.querySelector('[data-player-wrap]');
    if (!wrap) return;
    const iframe = wrap.querySelector('iframe.player');
    if (!iframe || !window.YT || !window.YT.Player) return;
    // S'assurer que l'iframe a un id (requis par YT.Player).
    if (!iframe.id) iframe.id = 'reco-yt-player';
    // Force enablejsapi sur l'URL si chargée.
    const src = iframe.getAttribute('src') || '';
    if (src && src !== 'about:blank' && !src.includes('enablejsapi=1')) {
      const sep = src.includes('?') ? '&' : '?';
      iframe.setAttribute('src', src + sep + 'enablejsapi=1');
    }
    try {
      __ytPlayer = new YT.Player(iframe.id, {
        events: {
          'onReady': () => { if (__ytReadyResolve) { __ytReadyResolve(__ytPlayer); __ytReadyResolve = null; } },
        },
      });
    } catch (_) { /* no-op */ }
  }

  function ytToggle() {
    // Si YT.Player n'est pas dispo, fallback via postMessage manuel.
    if (__ytPlayer && typeof __ytPlayer.getPlayerState === 'function') {
      const state = __ytPlayer.getPlayerState();
      // 1 = playing
      if (state === 1) __ytPlayer.pauseVideo();
      else __ytPlayer.playVideo();
      return;
    }
    const wrap = document.querySelector('[data-player-wrap]');
    const iframe = wrap && wrap.querySelector('iframe.player');
    if (!iframe || !iframe.contentWindow) return;
    // Best-effort : envoyer une commande playVideo (pas de toggle natif sans API).
    iframe.contentWindow.postMessage(
      JSON.stringify({ event: 'command', func: 'playVideo', args: [] }),
      '*'
    );
  }

  // Click le timecode de la carte active : recharge le player à ce timestamp.
  function clickActiveTimecode(li) {
    const target = li || getActiveRow();
    if (!target) return false;
    const a = target.querySelector('a.tc[target="ytplayer"]');
    if (!a) return false;
    a.click();
    return true;
  }

  // Auto-play : debounce 800ms (cf. brief) + ne touche au YT que si toggle ON.
  let __autoplayTimer = null;
  function scheduleAutoplay(li) {
    if (__autoplayTimer) clearTimeout(__autoplayTimer);
    __autoplayTimer = setTimeout(() => {
      clickActiveTimecode(li);
    }, 800);
  }

  function setAutoplay(on) {
    window.__recoAutoplayEnabled = !!on;
    try { localStorage.setItem('reco-autoplay', on ? '1' : '0'); } catch (_) {}
    const btn = document.querySelector('[data-autoplay-toggle]');
    if (btn) {
      btn.classList.toggle('on', !!on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.title = on ? 'Auto-play activé (cliquer pour désactiver)'
                     : 'Auto-play désactivé (cliquer pour activer)';
    }
  }

  function initAutoplayState() {
    let stored = '0';
    try { stored = localStorage.getItem('reco-autoplay') || '0'; } catch (_) {}
    setAutoplay(stored === '1');
  }

  // --- Search bar (touche /) ---
  function ensureSearchBar() {
    let bar = document.getElementById('reco-search-bar');
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'reco-search-bar';
    bar.hidden = true;
    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Rechercher (titre, créateur)… Esc pour fermer';
    input.id = 'reco-search-input';
    input.autocomplete = 'off';
    input.spellcheck = false;
    bar.appendChild(input);
    document.body.appendChild(bar);
    input.addEventListener('input', () => applySearchFilter(input.value));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeSearchBar();
      }
    });
    return bar;
  }

  function openSearchBar() {
    const bar = ensureSearchBar();
    bar.hidden = false;
    const input = bar.querySelector('input');
    if (input) {
      input.focus();
      input.select();
    }
  }

  function closeSearchBar() {
    const bar = document.getElementById('reco-search-bar');
    if (bar) bar.hidden = true;
    const input = document.getElementById('reco-search-input');
    if (input) {
      input.value = '';
      input.blur();
    }
    applySearchFilter('');
  }

  function applySearchFilter(q) {
    const needle = (q || '').trim().toLowerCase();
    document.querySelectorAll('li.row[data-reco-id]').forEach((li) => {
      if (!needle) {
        li.classList.remove('hidden-by-search');
        return;
      }
      const text = (li.textContent || '').toLowerCase();
      if (text.includes(needle)) {
        li.classList.remove('hidden-by-search');
      } else {
        li.classList.add('hidden-by-search');
      }
    });
  }

  // --- Help overlay (touche ?) ---
  function ensureHelpOverlay() {
    let ov = document.getElementById('reco-help-overlay');
    if (ov) return ov;
    ov = document.createElement('div');
    ov.id = 'reco-help-overlay';
    ov.hidden = true;
    const box = document.createElement('div');
    box.className = 'help-box';
    box.innerHTML = `
      <h2>Raccourcis clavier</h2>
      <div class="help-grid">
        <section><h3>Navigation</h3>
          <dl>
            <dt>J / ↓</dt><dd>Carte suivante</dd>
            <dt>K / ↑</dt><dd>Carte précédente</dd>
            <dt>Shift+J / Shift+K</dt><dd>Inclure les discarded</dd>
            <dt>[</dt><dd>Épisode précédent</dd>
            <dt>]</dt><dd>Épisode suivant</dd>
          </dl>
        </section>
        <section><h3>Actions</h3>
          <dl>
            <dt>V</dt><dd>Valider la carte active</dd>
            <dt>C</dt><dd>Marquer comme citation</dd>
            <dt>D</dt><dd>Discard (pas une reco)</dd>
            <dt>E</dt><dd>Éditer (toggle)</dd>
            <dt>R</dt><dd>Ré-enrichir</dd>
          </dl>
        </section>
        <section><h3>Lecteur</h3>
          <dl>
            <dt>Espace</dt><dd>Play / Pause YouTube</dd>
            <dt>T</dt><dd>Recharger au timecode actif</dd>
            <dt>🔁</dt><dd>Auto-play au changement de carte</dd>
          </dl>
        </section>
        <section><h3>Recherche</h3>
          <dl>
            <dt>/</dt><dd>Recherche locale (titre, créateur)</dd>
            <dt>? / Shift+/</dt><dd>Cette aide</dd>
            <dt>Esc</dt><dd>Fermer overlay / recherche / édition</dd>
          </dl>
        </section>
      </div>
      <p class="help-foot">Esc ou clic en dehors pour fermer.</p>
    `;
    ov.appendChild(box);
    ov.addEventListener('click', (e) => {
      if (e.target === ov) closeHelpOverlay();
    });
    document.body.appendChild(ov);
    return ov;
  }

  function openHelpOverlay() {
    const ov = ensureHelpOverlay();
    ov.hidden = false;
  }

  function closeHelpOverlay() {
    const ov = document.getElementById('reco-help-overlay');
    if (ov) ov.hidden = true;
  }

  // --- Autoplay toggle button (injecté dans merge-bar form ou flottant) ---
  function ensureAutoplayToggle() {
    if (document.querySelector('[data-autoplay-toggle]')) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('data-autoplay-toggle', '1');
    btn.id = 'reco-autoplay-toggle';
    btn.textContent = '🔁 Auto-play';
    btn.addEventListener('click', () => {
      setAutoplay(!window.__recoAutoplayEnabled);
    });
    document.body.appendChild(btn);
  }

  // --- Action helpers (V/C/D/R/E) ---
  function submitSaveAction(actionValue) {
    const li = getActiveRow();
    if (!li) return;
    const form = li.querySelector('form[action="/save"]');
    if (!form) return;
    // Crée un hidden `action` puis submit programmatiquement (les <button name=action>
    // ne soumettent leur value que si c'est eux qui ont déclenché le submit).
    let hidden = form.querySelector('input[type=hidden][name="action"]');
    if (!hidden) {
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'action';
      form.appendChild(hidden);
    }
    hidden.value = actionValue;
    form.submit();
  }

  function reenrichActive() {
    const li = getActiveRow();
    if (!li) return;
    const form = li.querySelector('form[action="/reenrich"]');
    if (!form) {
      toast('Cette reco n\'est pas ré-enrichissable', 'warning');
      return;
    }
    // AJAX path déjà câblé via le délégué submit — on dispatch un submit.
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    }
  }

  function toggleEditActive() {
    const li = getActiveRow();
    if (!li) return;
    const guid = getGuidFromUrl();
    if (!guid) return;
    const url = new URL(window.location.href);
    const currentEdit = url.searchParams.get('edit');
    const rid = li.getAttribute('data-reco-id') || '';
    if (currentEdit === rid) {
      url.searchParams.delete('edit');
    } else {
      url.searchParams.set('edit', rid);
    }
    window.location.href = url.toString();
  }

  function gotoSiblingEpisode(side) {
    const sel = side === 'prev' ? '.eph-arrow-prev' : '.eph-arrow-next';
    const a = document.querySelector('a' + sel);
    if (a && a.href) window.location.href = a.href;
  }

  // --- Keydown dispatcher ---
  function isEditableTarget(t) {
    if (!t) return false;
    if (!(t instanceof Element)) return false;
    return t.matches('input, textarea, select, [contenteditable], [contenteditable="true"]');
  }

  function onKeydown(e) {
    // Escape — toujours pris en compte (ferme overlay/search/édition).
    if (e.key === 'Escape') {
      const help = document.getElementById('reco-help-overlay');
      if (help && !help.hidden) { closeHelpOverlay(); e.preventDefault(); return; }
      const bar = document.getElementById('reco-search-bar');
      if (bar && !bar.hidden) { closeSearchBar(); e.preventDefault(); return; }
      // Fermer l'édition inline si ouverte (?edit=…).
      const url = new URL(window.location.href);
      if (url.searchParams.has('edit')) {
        url.searchParams.delete('edit');
        window.location.href = url.toString();
        e.preventDefault();
        return;
      }
      // Si focus est dans un input — laisse le navigateur gérer.
      return;
    }

    if (isEditableTarget(e.target)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    const k = e.key;
    const shifted = e.shiftKey;
    // J / ↓
    if (k === 'j' || k === 'J' || k === 'ArrowDown') {
      moveActive(1, shifted || !KB_ACTIVE_SKIP_DISCARDED);
      e.preventDefault(); return;
    }
    // K / ↑
    if (k === 'k' || k === 'K' || k === 'ArrowUp') {
      moveActive(-1, shifted || !KB_ACTIVE_SKIP_DISCARDED);
      e.preventDefault(); return;
    }
    // V — validate
    if (k === 'v' || k === 'V') { submitSaveAction('validate'); e.preventDefault(); return; }
    // C — citation
    if (k === 'c' || k === 'C') { submitSaveAction('citation'); e.preventDefault(); return; }
    // D — discard
    if (k === 'd' || k === 'D') { submitSaveAction('discard'); e.preventDefault(); return; }
    // E — édition inline
    if (k === 'e' || k === 'E') { toggleEditActive(); e.preventDefault(); return; }
    // R — re-enrich
    if (k === 'r' || k === 'R') { reenrichActive(); e.preventDefault(); return; }
    // Espace — play/pause YT
    if (k === ' ' || k === 'Spacebar') { ytToggle(); e.preventDefault(); return; }
    // T — recharge timecode
    if (k === 't' || k === 'T') {
      if (!clickActiveTimecode()) toast('Pas de timecode YouTube sur la carte active', 'info');
      e.preventDefault(); return;
    }
    // [ — épisode précédent
    if (k === '[') { gotoSiblingEpisode('prev'); e.preventDefault(); return; }
    // ] — épisode suivant
    if (k === ']') { gotoSiblingEpisode('next'); e.preventDefault(); return; }
    // / — recherche
    if (k === '/' && !shifted) { openSearchBar(); e.preventDefault(); return; }
    // ? (Shift+/) — overlay aide
    if (k === '?' || (k === '/' && shifted)) { openHelpOverlay(); e.preventDefault(); return; }
  }

  function initKeyboard() {
    document.addEventListener('keydown', onKeydown);
    ensureYTApi();
    // L'API peut s'instancier avant le callback global si déjà chargée.
    setTimeout(tryInstantiateYTPlayer, 100);
    initAutoplayState();
    ensureAutoplayToggle();
  }
  initOnReady(initKeyboard);

  // Quand un clic sur un timecode recharge l'iframe, on doit ré-instancier
  // le YT.Player (nouveau src → ancien player obsolète).
  document.addEventListener('click', (e) => {
    const tc = e.target.closest('a[target="ytplayer"]');
    if (!tc) return;
    // Reset & re-bind après que le nav ait chargé le nouveau src.
    __ytPlayer = null;
    setTimeout(tryInstantiateYTPlayer, 600);
  });


  // Publication pour le core (ajaxPost) + hooks de test.
  window.__reco.setActiveRow = setActiveRow;
  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      applySearchFilter: applySearchFilter,
      getRows: getRows,
    });
  }
})();
