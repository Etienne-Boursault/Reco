(() => {
  // Gate anti-double-init (listeners délégués sans namespace, cf. #37).
  if (window.__recoClientInit) return;
  window.__recoClientInit = true;

  // Helper : exécute fn dès que le DOM est prêt (déduplique 6 patterns).
  function initOnReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  // --- TOAST ---
  // Toast bas-droite, auto-disparait après 4s.
  function toast(message, kind) {
    const zone = document.getElementById('toast-zone');
    if (!zone) return;
    const el = document.createElement('div');
    el.className = 'toast toast-' + (kind || 'info');
    el.textContent = message;
    zone.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 300);
    }, 4000);
  }

  // --- REPLACE CARD / AJAX ---
  // Remplace la carte (li.row) qui contient la reco_id par le HTML reçu.
  // La carte DOIT n'utiliser QUE des listeners délégués sur document — un
  // attachement direct est perdu au remplacement.
  function replaceCard(reco_id, html) {
    if (!html) return;
    const current = document.querySelector('input[name="id"][value="' + CSS.escape(reco_id) + '"]');
    const li = current && current.closest('li.row');
    if (!li) return;
    const tmpl = document.createElement('template');
    tmpl.innerHTML = html.trim();
    const fresh = tmpl.content.firstElementChild;
    if (fresh) {
      // Préserve l'index d'origine (tri #2) sinon la carte remplacée après
      // une édition AJAX retomberait en tête de l'ordre chronologique.
      if (li.dataset.origIdx !== undefined && fresh.dataset) {
        fresh.dataset.origIdx = li.dataset.origIdx;
      }
      li.replaceWith(fresh);
    }
  }

  // Retire la carte d'une reco traitée (fondu) et déplace le focus sur la reco
  // suivante — sur /doutes, un doute validé/écarté disparaît de la file sans
  // rechargement de page (refonte 2026-07-21).
  function removeCard(reco_id) {
    const current = document.querySelector('input[name="id"][value="' + CSS.escape(reco_id) + '"]');
    const li = current && current.closest('li.row');
    if (!li) return;
    const rows = Array.from(document.querySelectorAll('li.row[data-reco-id]'));
    const idx = rows.indexOf(li);
    const next = rows[idx + 1] || rows[idx - 1] || null;
    li.style.transition = 'opacity .18s ease, transform .18s ease';
    li.style.opacity = '0';
    li.style.transform = 'translateX(1.5rem)';
    setTimeout(() => {
      li.remove();
      if (next && window.__reco.setActiveRow) {
        window.__reco.setActiveRow(next, { noAutoplay: true });
      }
    }, 180);
  }

  // Retire le paramètre ?edit= de l'URL sans recharger (history.replaceState).
  // #4 : après une édition AJAX réussie, l'URL gardait `&edit=ubm-xxxx`, si
  // bien qu'un refresh rouvrait le formulaire et que la carte fraîchement
  // remplacée n'était plus « active » (les raccourcis V/C/D ne l'atteignaient
  // plus). On nettoie donc le param dès la sauvegarde.
  function clearEditParamFromUrl() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('edit')) return;
    url.searchParams.delete('edit');
    window.history.replaceState({}, '', url.pathname + url.search + url.hash);
  }

  async function ajaxPost(action, formData, reco_id) {
    try {
      const r = await fetch(action, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: new URLSearchParams(formData),
      });
      const data = await r.json();
      // Sur /doutes : une action /save (validate/citation/discard/leur œuvre)
      // traite le doute → la carte DISPARAÎT de la file (au lieu d'être
      // remplacée par sa version « done »), et le focus passe à la suivante.
      const onDoutes = window.location.pathname === '/doutes';
      // Sur /doutes, /save ET /edit sont des décisions TERMINALES : le doute
      // traité (validé/écarté) ou corrigé DISPARAÎT de la file — le backend a
      // posé reviewedByHuman — au lieu d'être remplacé par sa carte « done ».
      // Le focus passe à la reco suivante (removeCard).
      if ((action === '/save' || action === '/edit') && onDoutes && data.kind !== 'error') {
        removeCard(reco_id);
      } else if (data.card_html) {
        replaceCard(reco_id, data.card_html);
      }
      if (data.message) toast(data.message, data.kind || 'info');
      // #4 — édition réussie : nettoie ?edit= et re-marque la carte active
      // pour que la validation clavier (V/C/D) agisse tout de suite dessus.
      // On NE nettoie PAS sur erreur de validation (le formulaire reste
      // ouvert pour correction).
      if (action === '/edit' && data.kind !== 'error') {
        clearEditParamFromUrl();
        // Sur /doutes la carte vient d'être retirée (édition terminale) → pas de
        // ré-activation. Ailleurs (/ep), on re-marque la carte fraîche active.
        if (!onDoutes) {
          const fresh = document.querySelector(
            'li.row[data-reco-id="' + CSS.escape(reco_id) + '"]'
          );
          if (fresh && window.__reco.setActiveRow) {
            window.__reco.setActiveRow(fresh, { noScroll: true, noAutoplay: true });
          }
        }
      }
    } catch (err) {
      toast('Erreur réseau : ' + err.message, 'error');
    }
  }

  // --- FLASH URL → TOAST ---
  // Au chargement : convertit un flash PRG (?flash=&kind=) en toast et
  // retire les paramètres de l'URL pour éviter la persistance au refresh.
  // Couvre aussi /rename-guest (non-AJAX) — pas besoin de bandeau.
  function consumeFlashFromUrl() {
    const qs = new URLSearchParams(window.location.search);
    const msg = qs.get('flash');
    if (!msg) return;
    const VALID_KINDS = new Set(['info', 'success', 'warning', 'error']);
    const rawKind = qs.get('kind');
    const kind = VALID_KINDS.has(rawKind) ? rawKind : 'info';
    toast(msg, kind);
    qs.delete('flash');
    qs.delete('kind');
    const clean = window.location.pathname
      + (qs.toString() ? '?' + qs.toString() : '')
      + window.location.hash;
    window.history.replaceState({}, '', clean);
    // Retire le bandeau serveur (devenu redondant).
    document.querySelectorAll('.flash').forEach((n) => n.remove());
  }
  initOnReady(consumeFlashFromUrl);

  // --- MANUAL MERGE ---
  // Fusion manuelle : sélection à la checkbox + barre flottante.
  function setupManualMerge() {
    const bar = document.querySelector('[data-merge-bar]');
    if (!bar) return;
    const counter = bar.querySelector('[data-merge-count]');
    const idsInput = bar.querySelector('[data-merge-ids]');
    const clearBtn = bar.querySelector('[data-merge-clear]');
    const submitBtn = bar.querySelector('button[type="submit"]');
    function update() {
      const checked = Array.from(
        document.querySelectorAll('[data-merge-select]:checked')
      );
      const ids = checked.map((c) => c.value);
      if (ids.length >= 1) {
        bar.hidden = false;
        counter.textContent = ids.length + ' reco' + (ids.length > 1 ? 's' : '')
          + ' sélectionnée' + (ids.length > 1 ? 's' : '');
        idsInput.value = ids.join(',');
        if (submitBtn) {
          submitBtn.disabled = ids.length < 2;
          submitBtn.title = ids.length < 2
            ? 'Sélectionne au moins 2 recos pour fusionner'
            : '';
        }
      } else {
        bar.hidden = true;
        idsInput.value = '';
      }
    }
    document.addEventListener('change', (e) => {
      const t = e.target;
      if (t instanceof HTMLInputElement && t.hasAttribute('data-merge-select')) {
        update();
      }
    });
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        document.querySelectorAll('[data-merge-select]:checked')
          .forEach((c) => { c.checked = false; });
        update();
      });
    }
    update();
  }
  initOnReady(setupManualMerge);

  // --- PLAYER DRAG ---
  // Le handle en haut-gauche permet de glisser l'encart où on veut.
  // On utilise des coords `top/left` absolus (en remplaçant le `right` initial).
  // Pointer events : unifie souris + tactile + stylus (cf. #23).
  // setPointerCapture garde les events sur le handle même quand le doigt /
  // la souris sort de sa hitbox — UX plus fluide.
  // `touch-action: none` sur [data-player-drag] (cf. review_server.css)
  // empêche le scroll natif pendant le drag tactile.
  function setupPlayerDrag() {
    const wrap = document.querySelector('[data-player-wrap]');
    if (!wrap) return;
    const handle = wrap.querySelector('[data-player-drag]');
    if (!handle) return;
    let dragging = false, startX = 0, startY = 0, startLeft = 0, startTop = 0;
    handle.addEventListener('pointerdown', (e) => {
      const rect = wrap.getBoundingClientRect();
      // On bascule en coords gauche/haut absolues une fois saisi.
      wrap.style.left = rect.left + 'px';
      wrap.style.top = rect.top + 'px';
      wrap.style.right = 'auto';
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      startLeft = rect.left;
      startTop = rect.top;
      try { handle.setPointerCapture(e.pointerId); } catch (_) { /* no-op */ }
      e.preventDefault();
    });
    handle.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const nl = Math.max(0, Math.min(window.innerWidth - 40, startLeft + e.clientX - startX));
      const nt = Math.max(0, Math.min(window.innerHeight - 40, startTop + e.clientY - startY));
      wrap.style.left = nl + 'px';
      wrap.style.top = nt + 'px';
    });
    function endDrag(e) {
      if (!dragging) return;
      dragging = false;
      try { handle.releasePointerCapture(e.pointerId); } catch (_) { /* no-op */ }
    }
    handle.addEventListener('pointerup', endDrag);
    handle.addEventListener('pointercancel', endDrag);
  }
  initOnReady(setupPlayerDrag);

  // --- PLAYER TOGGLE ---
  // ✕ vide l'iframe (about:blank pour stopper la lecture) et masque le bloc.
  // Tout clic sur un timecode (a[target="ytplayer"]) ré-affiche le bloc.
  function setupPlayerToggle() {
    const wrap = document.querySelector('[data-player-wrap]');
    if (!wrap) return;
    const iframe = wrap.querySelector('iframe.player');
    document.addEventListener('click', (e) => {
      const closeBtn = e.target.closest('[data-player-close]');
      if (closeBtn) {
        if (iframe) iframe.src = 'about:blank';
        wrap.classList.add('hidden');
        return;
      }
      const tc = e.target.closest('a[target="ytplayer"]');
      if (tc) wrap.classList.remove('hidden');
    });
  }
  initOnReady(setupPlayerToggle);

  // --- AJAX FORM SUBMIT (delegated) ---
  // Intercepte les submits sur les formulaires AJAX-able.
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    const action = form.getAttribute('action') || '';
    // /save inclus (refonte 2026-07-21) : Valider/Citation/Leur œuvre/Pas une
    // reco se faisaient en POST natif → rechargement + retour en haut de page.
    if (action !== '/edit' && action !== '/reenrich' && action !== '/save') return;
    e.preventDefault();
    const fd = new FormData(form);
    // FormData n'inclut PAS le bouton submit cliqué (name="action"
    // value=validate/citation/discard/guest-work) — on l'ajoute via e.submitter,
    // sinon le backend ne saurait pas quelle action appliquer.
    if (e.submitter && e.submitter.name) fd.set(e.submitter.name, e.submitter.value);
    const reco_id = fd.get('id');
    if (!reco_id) return;
    ajaxPost(action, fd, reco_id);
  });

  // --- NAMESPACE PARTAGÉ (M4 découpe en 3 fichiers) ---
  // Les helpers consommés par review_client_keyboard.js / _toolbar.js sont
  // publiés ici ; l'ordre de concaténation (core → keyboard → toolbar) est
  // garanti par review_render_common._CLIENT_JS.
  window.__reco = window.__reco || {};
  Object.assign(window.__reco, { initOnReady: initOnReady, toast: toast });
  // Hooks de test (jamais définis en prod — cf. tests/js/).
  if (window.__recoTestHooks) {
    Object.assign(window.__recoTestHooks, {
      clearEditParamFromUrl: clearEditParamFromUrl,
    });
  }
})();
