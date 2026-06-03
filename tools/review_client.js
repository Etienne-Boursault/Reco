(() => {
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

  // Remplace la carte (li.row) qui contient la reco_id par le HTML reçu.
  function replaceCard(reco_id, html) {
    if (!html) return;
    const current = document.querySelector('input[name="id"][value="' + CSS.escape(reco_id) + '"]');
    const li = current && current.closest('li.row');
    if (!li) return;
    const tmpl = document.createElement('template');
    tmpl.innerHTML = html.trim();
    const fresh = tmpl.content.firstElementChild;
    if (fresh) li.replaceWith(fresh);
  }

  async function ajaxPost(action, formData, reco_id) {
    try {
      const r = await fetch(action, {
        method: 'POST',
        headers: { 'Accept': 'application/json' },
        body: new URLSearchParams(formData),
      });
      const data = await r.json();
      if (data.card_html) replaceCard(reco_id, data.card_html);
      if (data.message) toast(data.message, data.kind || 'info');
    } catch (err) {
      toast('Erreur réseau : ' + err.message, 'error');
    }
  }

  // Au chargement : convertit un flash PRG (?flash=&kind=) en toast et
  // retire les paramètres de l'URL pour éviter la persistance au refresh.
  // Couvre aussi /rename-guest (non-AJAX) — pas besoin de bandeau.
  function consumeFlashFromUrl() {
    const qs = new URLSearchParams(window.location.search);
    const msg = qs.get('flash');
    if (!msg) return;
    const kind = qs.get('kind') || 'info';
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
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', consumeFlashFromUrl);
  } else {
    consumeFlashFromUrl();
  }

  // Délégation : intercepte les submits sur les formulaires AJAX-able.
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    const action = form.getAttribute('action') || '';
    if (action !== '/edit' && action !== '/reenrich') return;
    e.preventDefault();
    const fd = new FormData(form);
    const reco_id = fd.get('id');
    if (!reco_id) return;
    ajaxPost(action, fd, reco_id);
  });
})();
