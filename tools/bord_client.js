/**
 * bord_client.js — le script de `/bord`, le tableau de bord d'admin de Reco V1.
 *
 * Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, vue
 * 39 pouces par défaut (plan `pr-tableau-de-bord.md`, § 5, tranche 1d-2).
 *
 * Recopié en ligne dans la page par `bord_rendu.py` (la CSP n'admet que du
 * script en ligne). Sans lui, tout marche encore : la vue suit la largeur, et
 * une case part en formulaire classique, renvoyé par une redirection 303.
 *
 * - Le choix de la vue : révèle `.bord-vues`, pose `data-vue` sur `<html>` et
 *   le garde dans `localStorage["bord-vue"]` (relu par le script de `<head>`).
 *   Un stockage refusé n'empêche pas de changer de vue pour cette page.
 * - Les cases des réseaux : le formulaire part en `fetch` (`Accept: JSON`), et
 *   la case change sans recharger. Si `fetch` est rejeté (panne réseau), le
 *   formulaire repart à l'ancienne : sans risque, `fait` porte la valeur
 *   voulue, pas une bascule. Une réponse qui n'est pas du JSON (403, 413)
 *   laisse la case telle quelle et affiche une erreur (tour 1, F4).
 */
(() => {
  const racine = document.documentElement;
  const VUES = ['auto', '39', '13', 'telephone'];
  const GENRES = ['success', 'warning', 'error', 'info'];

  function marquerVue(vue) {
    racine.setAttribute('data-vue', vue);
    document.querySelectorAll('[data-vue-choix]').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-vue-choix') === vue));
    });
  }

  function choisirVue(vue) {
    if (VUES.indexOf(vue) < 0) return;
    marquerVue(vue);
    try {
      window.localStorage.setItem('bord-vue', vue);
    } catch (e) {
      console.warn('bord : la vue « ' + vue + ' » vaut pour cette page seulement', e);
    }
  }

  // Le bandeau des messages, celui de la redirection 303 s'il est déjà là.
  function message(texte, genre) {
    let el = document.querySelector('.flash');
    if (!el) {
      el = document.createElement('div');
      el.setAttribute('role', 'status');
      document.querySelector('.bord-entete').after(el);
    }
    el.className = 'flash flash-' + (GENRES.indexOf(genre) >= 0 ? genre : 'info');
    el.textContent = texte;
  }

  function poserCase(form, fait) {
    const b = form.querySelector('button.bord-case');
    b.setAttribute('data-fait', fait ? '1' : '0');
    b.textContent = fait ? '✓' : 'À faire';
    const action = fait ? 'décocher' : 'marquer comme fait';
    b.setAttribute('aria-label', b.getAttribute('aria-label').replace(/ : [^:]*$/, ' : ' + action));
    if (fait) {
      const d = new Date();
      const jj = (n) => String(n).padStart(2, '0');
      b.setAttribute('title', 'coché le ' + jj(d.getDate()) + '/' + jj(d.getMonth() + 1));
    } else {
      b.removeAttribute('title');
    }
    form.elements.namedItem('fait').value = fait ? '0' : '1';
  }

  async function envoyer(form) {
    const b = form.querySelector('button.bord-case');
    const voulu = form.elements.namedItem('fait').value === '1';
    b.disabled = true;
    let r;
    try {
      r = await fetch(form.action, {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: new URLSearchParams(new FormData(form)),
      });
    } catch (e) {
      // Seule une panne du réseau relance le formulaire classique (tour 1, F4).
      console.warn('bord : envoi de la case en direct impossible, envoi classique', e);
      form.submit();
      b.disabled = false;
      return;
    }
    // Un refus qui n'est pas du JSON (403, 413) laisse la case telle quelle.
    const data = await r.json().catch(() => null);
    if (!data || !r.ok || data.kind === 'error') {
      message((data && data.message) || "La case n'a pas été enregistrée.", 'error');
    } else {
      poserCase(form, voulu);
      if (data.message) message(data.message, data.kind);
    }
    b.disabled = false;
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-vue-choix]');
    if (b) choisirVue(b.getAttribute('data-vue-choix'));
  });
  document.addEventListener('submit', (e) => {
    const form = e.target.closest('form.bord-case-form');
    if (!form) return;
    e.preventDefault();
    envoyer(form);
  });

  document.querySelector('.bord-vues').hidden = false;
  marquerVue(racine.getAttribute('data-vue'));
})();
