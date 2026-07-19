(() => {
  // review_client_cluster.js — ajout/retrait manuel d'une reco à un cluster de
  // doublons. Découpé de review_client.js (M4 CR cumulative — limite 500
  // lignes). Chargé APRÈS le core : consomme window.__reco.{initOnReady,toast}.
  if (window.__recoClusterInit) return;
  window.__recoClusterInit = true;
  const initOnReady = window.__reco.initOnReady;
  const toast = window.__reco.toast;

  // --- CLUSTER ADD / REMOVE ---
  // Ajout manuel d'une reco à un cluster déjà rendu.
  // Le serveur expose un <select data-cluster-add> dans chaque cluster card,
  // listant les autres recos du même épisode. Quand l'utilisateur en choisit
  // une, on :
  //   1. récupère la <li.row data-reco-id="X"> ailleurs dans la page ;
  //   2. la déplace DANS la cluster card (avant la barre d'actions) ;
  //   3. ajoute son id au hidden `cluster_ids` du form cluster ;
  //   4. injecte un <input type="radio" name="keep_id" value="X"> pour la
  //      rendre éligible comme canonical (non coché par défaut — on garde
  //      celui pré-sélectionné par le serveur).
  // Pour la barre de fusion manuelle (data-merge-bar), on coche aussi sa
  // checkbox merge-select au cas où l'utilisateur préférerait passer par la
  // barre flottante.
  // Construit le <label.cluster-option.cluster-added> sans innerHTML.
  // id sur le radio + for sur le label pour l'accessibilité.
  function buildAddedOption(rid, titleTxt) {
    const label = document.createElement('label');
    label.className = 'cluster-option cluster-added';
    label.dataset.addedRid = rid;
    const radioId = 'keep-added-' + rid;
    label.setAttribute('for', radioId);

    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'keep_id';
    radio.value = rid;
    radio.id = radioId;
    radio.dataset.addedRid = rid;

    const bold = document.createElement('b');
    bold.textContent = titleTxt || rid;

    const meta = document.createElement('span');
    meta.className = 'cluster-meta';
    meta.textContent = '(ajoutée manuellement)';

    label.appendChild(radio);
    label.appendChild(document.createTextNode(' '));
    label.appendChild(bold);
    label.appendChild(document.createTextNode(' '));
    label.appendChild(meta);
    return label;
  }

  // Wrap la <li.row> dans un .cluster-added-row + bouton « × retirer ».
  function buildAddedRowWrap(rid, srcLi) {
    const wrap = document.createElement('div');
    wrap.className = 'cluster-added-row';
    wrap.dataset.addedRid = rid;

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'cluster-added-remove';
    removeBtn.dataset.removeFromCluster = rid;
    removeBtn.textContent = '× retirer';
    removeBtn.title = 'Retirer cette reco du cluster';

    wrap.appendChild(removeBtn);
    wrap.appendChild(srcLi);
    return wrap;
  }

  // Vérifie qu'une reco n'est pas déjà engagée dans un AUTRE cluster.
  function findOwningCluster(rid) {
    const forms = document.querySelectorAll('form.cluster-form input[name="cluster_ids"]');
    for (const inp of forms) {
      const ids = inp.value.split(',').filter(Boolean);
      if (ids.includes(rid)) return inp.closest('form.cluster-form');
    }
    return null;
  }

  // Ajoute une reco au cluster (form). Retourne true en cas de succès.
  function addToCluster(rid, clusterForm) {
    const card = clusterForm.closest('li.row.cluster');
    if (!card) return false;
    const idsInput = clusterForm.querySelector('input[name="cluster_ids"]');
    if (!idsInput) return false;
    const ids = idsInput.value.split(',').filter(Boolean);
    // Idempotence : déjà membre.
    if (ids.includes(rid)) {
      toast('Cette reco est déjà dans le cluster', 'info');
      return false;
    }
    // Déjà dans un autre cluster ?
    const otherForm = findOwningCluster(rid);
    if (otherForm && otherForm !== clusterForm) {
      toast('Cette reco est déjà dans un autre cluster', 'error');
      return false;
    }
    // Source dans le DOM (hors cluster).
    const src = document.querySelector(
      'li.row[data-reco-id="' + CSS.escape(rid) + '"]'
    );
    if (!src) {
      toast('Reco introuvable côté UI', 'error');
      return false;
    }
    // Mémorise la liste parente d'origine pour pouvoir remettre la <li> en
    // cas de retrait (sinon on tombera en fallback : la <ul> la plus proche).
    if (!src.dataset.originalParentSel) {
      const origUl = src.parentElement;
      if (origUl && origUl.tagName === 'UL') {
        // On accroche un attribut sentinelle sur l'UL pour la retrouver.
        if (!origUl.dataset.recoListId) {
          origUl.dataset.recoListId = 'reco-list-' + Math.random().toString(36).slice(2, 9);
        }
        src.dataset.originalParentSel = origUl.dataset.recoListId;
      }
    }

    ids.push(rid);
    idsInput.value = ids.join(',');

    const title = src.querySelector('b');
    const titleTxt = title ? title.textContent : rid;
    const opts = card.querySelector('.cluster-options');
    if (opts) opts.appendChild(buildAddedOption(rid, titleTxt));

    const wrap = buildAddedRowWrap(rid, src);
    const actions = card.querySelector('.cluster-actions');
    if (actions) {
      clusterForm.insertBefore(wrap, actions);
    } else {
      clusterForm.appendChild(wrap);
    }

    // Décoche la merge-select : la reco est désormais gérée par le cluster
    // (via keep_id), il ne faut PAS qu'elle soit aussi comptée dans la barre
    // de fusion flottante (cf. #21).
    const cb = src.querySelector('[data-merge-select]');
    if (cb && cb.checked) {
      cb.checked = false;
      cb.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Retire l'option choisie du <select>.
    const sel = card.querySelector('select[data-cluster-add]');
    if (sel) {
      const opt = sel.querySelector('option[value="' + CSS.escape(rid) + '"]');
      if (opt) opt.remove();
      sel.value = '';
    }
    return true;
  }

  // Retire une reco du cluster : remet la <li.row> en fin de la <ul> d'origine
  // (ou en fallback dans la <ul> ancêtre), ré-injecte l'option dans le select,
  // décoche la merge-select, retire le radio keep_id et le wrap.
  function removeFromCluster(rid, clusterForm) {
    const card = clusterForm.closest('li.row.cluster');
    if (!card) return false;
    const idsInput = clusterForm.querySelector('input[name="cluster_ids"]');
    if (!idsInput) return false;

    const wrap = clusterForm.querySelector(
      '.cluster-added-row[data-added-rid="' + CSS.escape(rid) + '"]'
    );
    const srcLi = wrap ? wrap.querySelector('li.row[data-reco-id="' + CSS.escape(rid) + '"]') : null;

    // Retire du cluster_ids.
    const ids = idsInput.value.split(',').filter(Boolean).filter((x) => x !== rid);
    idsInput.value = ids.join(',');

    // Retire le radio keep_id ajouté + son label.
    const addedRadio = card.querySelector(
      '.cluster-options .cluster-added[data-added-rid="' + CSS.escape(rid) + '"]'
    );
    if (addedRadio) addedRadio.remove();

    // Ré-injecte l'option dans le <select>.
    const sel = card.querySelector('select[data-cluster-add]');
    if (sel && srcLi) {
      const title = srcLi.querySelector('b');
      const titleTxt = title ? title.textContent.trim() : rid;
      // Vérifie qu'on ne re-double pas l'option (au cas où).
      const existing = sel.querySelector('option[value="' + CSS.escape(rid) + '"]');
      if (!existing) {
        const opt = document.createElement('option');
        opt.value = rid;
        opt.textContent = titleTxt;
        sel.appendChild(opt);
      }
    }

    // Décoche la merge-select + trigger change.
    if (srcLi) {
      const cb = srcLi.querySelector('[data-merge-select]');
      if (cb) {
        cb.checked = false;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    // Remet la <li.row> à sa place : <ul> d'origine si retrouvable, sinon
    // la <ul> ancêtre du cluster card.
    if (srcLi) {
      let target = null;
      const origId = srcLi.dataset.originalParentSel;
      if (origId) {
        target = document.querySelector('ul[data-reco-list-id="' + origId + '"]');
      }
      if (!target) {
        target = card.closest('ul');
      }
      if (target) {
        target.appendChild(srcLi);
      } else if (wrap && wrap.parentNode) {
        wrap.parentNode.insertBefore(srcLi, wrap);
      }
    }

    // Retire le wrap.
    if (wrap) wrap.remove();
    return true;
  }

  // Branche les deux listeners délégués cluster : ajout (change sur le
  // <select data-cluster-add>) et retrait (click sur [data-remove-from-cluster]).
  // Nom explicite « AddRemove » pour qu'un futur lecteur cherchant
  // `removeFromCluster` retrouve facilement le point d'attache.
  function setupClusterAddRemove() {
    document.addEventListener('change', (e) => {
      const sel = e.target;
      if (!(sel instanceof HTMLSelectElement)) return;
      if (!sel.hasAttribute('data-cluster-add')) return;
      const rid = sel.value;
      if (!rid) return;
      const card = sel.closest('li.row.cluster');
      if (!card) return;
      const form = card.querySelector('form.cluster-form');
      if (!form) return;
      // Disable pendant l'op pour éviter le double-clic.
      sel.disabled = true;
      try {
        const ok = addToCluster(rid, form);
        if (!ok) {
          // Reset le select au placeholder si l'ajout n'a pas eu lieu.
          sel.value = '';
        }
      } catch (err) {
        // Sans ce catch, le finally masquerait l'exception (cf. review #23).
        toast('Erreur ajout : ' + err.message, 'error');
        sel.value = '';
      } finally {
        sel.disabled = false;
      }
    });

    // Délégué : bouton « × retirer » sur les rows ajoutées manuellement.
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-remove-from-cluster]');
      if (!btn) return;
      e.preventDefault();
      const rid = btn.getAttribute('data-remove-from-cluster');
      const form = btn.closest('form.cluster-form');
      if (!rid || !form) return;
      btn.disabled = true;
      try {
        removeFromCluster(rid, form);
      } catch (err) {
        toast('Erreur retrait : ' + err.message, 'error');
      } finally {
        btn.disabled = false;
      }
    });
  }
  initOnReady(setupClusterAddRemove);

  // --- ARTIST MODE (edit form) ---
  // Quand seul le type « artiste » est coché, on renomme l'étiquette Titre
  // en Nom et on cache le champ Créateur (le nom EST l'identité de l'artiste).
  function updateArtistMode(form) {
    const types = Array.from(form.querySelectorAll('input[name="types"]:checked'))
      .map((c) => c.value);
    const artistOnly = types.length === 1 && types[0] === 'artiste';
    const titleLbl = form.querySelector('[data-label="title"]');
    const creatorWrap = form.querySelector('[data-label="creator-wrap"]');
    if (titleLbl) titleLbl.textContent = artistOnly ? 'Nom' : 'Titre';
    if (creatorWrap) creatorWrap.style.display = artistOnly ? 'none' : '';
  }
  document.addEventListener('change', (e) => {
    const t = e.target;
    if (!(t instanceof HTMLInputElement)) return;
    if (t.name !== 'types') return;
    const form = t.closest('.edit-form');
    if (form) updateArtistMode(form);
  });
  function initArtistMode() {
    document.querySelectorAll('.edit-form').forEach(updateArtistMode);
  }
  initOnReady(initArtistMode);

})();
