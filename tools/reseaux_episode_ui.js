// reseaux_episode_ui.js — ajouts aux playlists Spotify et Deezer et aux listes
// SensCritique, depuis le navigateur (voir docs/reseaux-episode.md).
//
// Aucune de ces plateformes n'ouvre d'API d'ecriture a un compte sans
// abonnement : on passe par les requetes que leur propre site emploie, depuis
// un onglet connecte au compte « Une Bonne Reco ». Chaque bloc se colle dans
// l'onglet de sa plateforme ; les fonctions relisent la liste apres chaque
// ecriture et disent si le resultat est conforme.

// --- Spotify (onglet open.spotify.com) -------------------------------------
// Capte les en-tetes du lecteur au passage d'une requete, puis lit et modifie
// les playlists par spclient. Marche fenetre masquee, contrairement a la liste
// virtualisee de l'interface.
window.__spCapter = async () => {
  if (window.__hdr) return 'deja capte';
  const f0 = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === 'string' ? input : input.url;
      const h = new Headers((init && init.headers) || (input && input.headers) || {});
      if (h.get('authorization') && /spclient|api-partner/.test(url)) {
        window.__hdr = { auth: h.get('authorization'), ct: h.get('client-token') };
      }
    } catch (e) { /* requete sans en-tetes lisibles */ }
    return f0.apply(this, arguments);
  };
  history.pushState({}, '', '/collection/playlists');
  window.dispatchEvent(new PopStateEvent('popstate', { state: {} }));
  for (let i = 0; i < 40 && !window.__hdr; i++) await new Promise((r) => setTimeout(r, 250));
  return window.__hdr ? 'capte' : 'pas de requete du lecteur : recharger la page et recommencer';
};
const spEntetes = (json) => Object.assign(
  { authorization: window.__hdr.auth, 'client-token': window.__hdr.ct, accept: 'application/json' },
  json ? { 'content-type': 'application/json;charset=UTF-8' } : {});
const spBase = (pl) => 'https://spclient.wg.spotify.com/playlist/v2/playlist/' + pl;

window.__spLire = async (pl) => {
  const j = await (await fetch(spBase(pl) + '?decorate=revision,length', { headers: spEntetes() })).json();
  let items = j.contents.items;
  while (items.length < j.length) {
    const k = await (await fetch(spBase(pl) + '?from=' + items.length + '&length=100', { headers: spEntetes() })).json();
    if (!k.contents.items.length) break;
    items = items.concat(k.contents.items);
  }
  return { revision: j.revision, ids: items.map((i) => i.uri.split(':').pop()) };
};
const spChanger = async (pl, revision, op) => fetch(spBase(pl) + '/changes', {
  method: 'POST',
  headers: spEntetes(true),
  body: JSON.stringify({
    baseRevision: revision,
    deltas: [{ ops: [op], info: { source: { client: 'WEBPLAYER' } } }],
    wantResultingRevisions: false, wantSyncResult: false, nonces: [],
  }),
});

// Ajoute en fin de liste, dans l'ordre donne, les titres absents.
window.__spAjouter = async (pl, ids) => {
  const avant = await __spLire(pl);
  const nouveaux = ids.filter((i) => !avant.ids.includes(i));
  if (!nouveaux.length) return 'rien a ajouter, ' + avant.ids.length + ' titres';
  const items = nouveaux.map((i) => ({ uri: 'spotify:track:' + i, attributes: { timestamp: String(Date.now()) } }));
  const r = await spChanger(pl, avant.revision, { kind: 'ADD', add: { addLast: true, items } });
  const apres = await __spLire(pl);
  const conforme = JSON.stringify(apres.ids) === JSON.stringify(avant.ids.concat(nouveaux));
  return `statut ${r.status}, ${avant.ids.length} -> ${apres.ids.length}, conforme: ${conforme}`;
};

// Retire un titre sans toucher a l'ordre des autres.
window.__spRetirer = async (pl, id) => {
  const avant = await __spLire(pl);
  const k = avant.ids.indexOf(id);
  if (k < 0) return 'absent';
  const op = { kind: 'REM', rem: { fromIndex: k, length: 1, items: [{ uri: 'spotify:track:' + id }], itemsAsKey: false } };
  const r = await spChanger(pl, avant.revision, op);
  const apres = await __spLire(pl);
  const conforme = JSON.stringify(apres.ids) === JSON.stringify(avant.ids.filter((_, i) => i !== k));
  return `statut ${r.status}, ${avant.ids.length} -> ${apres.ids.length}, conforme: ${conforme}`;
};

// ISRC de chaque titre, pour retrouver le meme enregistrement sur Deezer :
// renvoie « id=ISRC id=ISRC … », a passer a tools/playlists_deezer.py.
window.__spIsrc = async (ids) => {
  const A = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const gid = (b62) => {
    let n = 0n;
    for (const c of b62) n = n * 62n + BigInt(A.indexOf(c));
    return n.toString(16).padStart(32, '0');
  };
  const sortie = [];
  for (const id of ids) {
    const url = 'https://spclient.wg.spotify.com/metadata/4/track/' + gid(id) + '?market=from_token';
    const j = await (await fetch(url, { headers: spEntetes() })).json();
    sortie.push(id + '=' + (((j.external_id || []).find((x) => x.type === 'isrc') || {}).id || '-'));
  }
  return sortie.join(' ');
};

// --- Deezer (onglet www.deezer.com) ------------------------------------------
window.__dzGw = async (method, body) => {
  const gw = (m, tok, b) => fetch(`/ajax/gw-light.php?method=${m}&input=3&api_version=1.0&api_token=${tok}`,
    { method: 'POST', credentials: 'include', body: JSON.stringify(b) }).then((r) => r.json());
  if (!window.__dzTok) {
    const u = await gw('deezer.getUserData', '', {});
    window.__dzTok = u.results.checkForm;
    window.__dzCompte = u.results.USER.BLOG_NAME;
  }
  return gw(method, window.__dzTok, body);
};
window.__dzLire = async (pl) => {
  let ids = [];
  let url = `https://api.deezer.com/playlist/${pl}/tracks?limit=100&_=${Date.now()}`;
  while (url) {
    const d = await (await fetch(url)).json();
    ids = ids.concat(d.data.map((t) => t.id));
    url = d.next;
  }
  return ids;
};
window.__dzAjouter = async (pl, ids) => {
  const avant = await __dzLire(pl);
  const nouveaux = ids.filter((i) => !avant.includes(i));
  if (!nouveaux.length) return 'rien a ajouter, ' + avant.length + ' titres';
  const r = await __dzGw('playlist.addSongs', { playlist_id: String(pl), songs: nouveaux.map((i) => [i, 0]), offset: -1 });
  await new Promise((x) => setTimeout(x, 1500));
  const apres = await __dzLire(pl);
  const conforme = JSON.stringify(apres) === JSON.stringify(avant.concat(nouveaux));
  return `${window.__dzCompte} | ${JSON.stringify(r.results)} | ${avant.length} -> ${apres.length}, conforme: ${conforme}`;
};
window.__dzRetirer = async (pl, ids) => {
  const r = await __dzGw('playlist.deleteSongs', { playlist_id: String(pl), songs: ids.map((i) => [i, 0]) });
  return JSON.stringify(r.results);
};

// --- SensCritique (onglet www.senscritique.com) -------------------------------
// Capte les en-tetes du client GraphQL du site au passage d'une requete.
window.__scCapter = async () => {
  if (window.__scEntetes) return 'deja capte';
  const f0 = window.fetch;
  window.fetch = async (...a) => {
    try {
      const [u, o] = a;
      if (String(u).includes('apollo.senscritique') && o && o.headers) {
        window.__scEntetes = o.headers instanceof Headers ? Object.fromEntries(o.headers.entries()) : { ...o.headers };
        window.__scUrl = String(u);
      }
    } catch (e) { /* requete sans en-tetes lisibles */ }
    return f0(...a);
  };
  window.scrollTo(0, document.body.scrollHeight);
  for (let i = 0; i < 40 && !window.__scEntetes; i++) await new Promise((r) => setTimeout(r, 250));
  return window.__scEntetes ? 'capte' : 'pas de requete : naviguer dans le site (une liste, une recherche) puis relancer';
};
const scGql = async (body) => (await fetch(window.__scUrl, {
  method: 'POST', headers: window.__scEntetes, body: JSON.stringify(body),
})).json();

// Candidats pour une oeuvre : « titre [annee] createurs (id) », a choisir a la main.
// univers : movie, tvShow, book, comicBook ; la recherche echoue sans l'id de la liste.
window.__scChercher = async (titre, univers, listId) => {
  const q = 'query S($keywords:String!,$universe:String,$limit:Int,$listId:Int,$offset:Int,$showAlreadyInList:Boolean){'
    + 'searchResult(keywords:$keywords,universe:$universe,limit:$limit,listId:$listId,offset:$offset,'
    + 'showAlreadyInList:$showAlreadyInList){results{products_list{id title originalTitle displayedYear '
    + 'yearOfProduction directors{name} creators{name} authors{name}}}}}';
  const variables = { keywords: titre, universe: univers, limit: 6, listId, offset: 0, showAlreadyInList: true };
  const j = await scGql({ operationName: 'S', variables, query: q });
  if (j.errors) throw new Error(JSON.stringify(j.errors).slice(0, 200));
  return (j.data.searchResult.results || []).flatMap((r) => r.products_list || []).map((c) => {
    const qui = [...(c.directors || []), ...(c.creators || []), ...(c.authors || [])].map((p) => p.name).slice(0, 2);
    return `${c.title} [${c.yearOfProduction || c.displayedYear}] ${qui.join(' et ')} (${c.id})`;
  });
};

// Ajoute une oeuvre a une liste, en tete par defaut (les listes vont du plus
// recent au plus ancien), avec le lien vers sa fiche sur le site.
window.__scAjouter = async (listId, scId, fiche, position = 1) => {
  const q = 'mutation A($listId:Int!,$annotation:String,$itemId:Int!,$position:Int){'
    + 'userListAddItem(annotation:$annotation,itemId:$itemId,listId:$listId,position:$position){position}}';
  const annotation = 'Recommandé dans Un Bon Moment : https://unebonnere.co/un-bon-moment/oeuvre/' + fiche + '/';
  const j = await scGql({ operationName: 'A', variables: { listId, itemId: scId, annotation, position }, query: q });
  if (j.errors) return JSON.stringify(j.errors).includes('already been added') ? 'deja dans la liste' : JSON.stringify(j.errors).slice(0, 200);
  return 'ok, position ' + j.data.userListAddItem.position;
};
