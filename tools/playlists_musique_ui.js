// playlists_musique_ui.js — ajouter des titres aux playlists Spotify par le
// lecteur web, sans API (voir tools/playlists_musique.py).
//
// A coller dans la console d'un onglet open.spotify.com connecte au compte
// « Une Bonne Reco », la fenetre visible. Puis, pour chaque playlist :
//   await __lotSp('Saison 6', [...ids], 'Un Bon Moment — Saison 6')
// Les titres ajoutes sont notes dans localStorage (`sp:faits:<cle>`) : relancer
// reprend ou l'on s'etait arrete. `__vider(idPlaylist, cle)` retire tout,
// titre par titre, avant une reconstruction.
//
// Le lecteur ajoute toujours en fin de liste ; le sous-menu « Ajouter a la
// playlist » ne s'ouvre qu'au survol ; une boite « Deja ajoute » se ferme par
// « Ne pas ajouter ». Ouvrir une page de titre peut lancer la lecture : on
// remet en pause apres chaque ajout.

window.__att = (ms) => new Promise((r) => setTimeout(r, ms));
window.__attendre = async (f, ms) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const v = f();
    if (v) return v;
    await __att(150);
  }
  return null;
};
window.__aller = async (chemin) => {
  history.pushState({}, '', chemin);
  window.dispatchEvent(new PopStateEvent('popstate', { state: {} }));
  await __att(2500);
};
window.__survol = (el) => {
  for (const t of ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointermove', 'mousemove']) {
    el.dispatchEvent(new MouseEvent(t, { bubbles: !t.includes('enter') }));
  }
};
window.__pause = () => {
  const pp = document.querySelector('[data-testid="control-button-playpause"]');
  if (pp && pp.ariaLabel === 'Pause') pp.click();
};
const menus = () => Array.from(document.querySelectorAll('[role="menu"]'));
const entree = (menu, texte) =>
  Array.from(menu.querySelectorAll('[role="menuitem"]')).find((x) => x.textContent.trim() === texte);

window.__ajout1 = async (id, nom) => {
  await __aller('/track/' + id);
  const plus = '[data-testid="action-bar-row"] [data-testid="more-button"]';
  if (!(await __attendre(() => location.pathname === '/track/' + id && document.querySelector(plus), 8000))) {
    throw new Error('pas de bouton');
  }
  await __att(700);
  document.querySelector(plus).click();
  const item = await __attendre(() => menus()[0] && entree(menus()[0], 'Ajouter à la playlist'), 4000);
  if (!item) throw new Error('pas de menu');
  __survol(item);
  const cible = await __attendre(() => menus().length > 1 && entree(menus()[menus().length - 1], nom), 4000);
  if (!cible) {
    document.body.click();
    throw new Error('pas de playlist');
  }
  cible.click();
  await __att(1200);
  __pause();
  const deja = Array.from(document.querySelectorAll('[role="dialog"] button, [role="alertdialog"] button'))
    .find((x) => /Ne pas ajouter/.test(x.textContent));
  if (deja) {
    deja.click();
    return 'doublon';
  }
  return 'ok';
};

window.__lotSp = async (cle, ids, nom) => {
  const fk = 'sp:faits:' + cle;
  const faits = JSON.parse(localStorage.getItem(fk) || '[]');
  const echecs = [];
  for (const id of ids) {
    if (faits.includes(id)) continue;
    let r = 'err';
    for (let essai = 0; essai < 2 && !['ok', 'doublon'].includes(r); essai++) {
      try { r = await __ajout1(id, nom); } catch (e) { r = 'err ' + e.message; }
    }
    if (['ok', 'doublon'].includes(r)) {
      faits.push(id);
      localStorage.setItem(fk, JSON.stringify(faits));
    } else {
      // Un titre manque : on s'arrete plutot que d'ajouter les suivants avant lui.
      echecs.push(id + ' ' + r);
      break;
    }
    await __att(600);
  }
  return `${faits.length}/${ids.length}` + (echecs.length ? ' — arret sur ' + echecs[0] : '');
};

// Une playlist vide affiche des recommandations sous la meme forme de lignes :
// on s'arrete quand plus aucune ligne ne propose « Supprimer de cette playlist ».
window.__vider = async (idPlaylist) => {
  await __aller('/playlist/' + idPlaylist);
  const premier = () => document.querySelector('main [data-testid="tracklist-row"] a[href*="/track/"]');
  let retires = 0;
  for (let rates = 0; rates < 4 && retires < 1000;) {
    const ligne = document.querySelector('main [data-testid="tracklist-row"]');
    if (!ligne) { rates++; await __att(1000); continue; }
    const avant = premier()?.getAttribute('href');
    ligne.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, clientX: 300, clientY: 300 }));
    const retirer = await __attendre(() => menus()[0] && entree(menus()[0], 'Supprimer de cette playlist'), 2500);
    if (!retirer) {
      rates++;
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await __att(600);
      continue;
    }
    rates = 0;
    retirer.click();
    retires++;
    await __attendre(() => premier()?.getAttribute('href') !== avant, 4000);
  }
  return retires;
};
